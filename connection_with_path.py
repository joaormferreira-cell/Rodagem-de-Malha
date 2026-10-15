import re
import time
import pandas as pd
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import socket

_CELL_RANGE_RE = re.compile(r"^([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)$")


def _col_letters_to_index(letters: str) -> int:
    n = 0
    for c in letters.upper():
        if not ("A" <= c <= "Z"):
            raise ValueError(f"invalid column letters: {letters!r}")
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n


def _index_to_col_letters(index: int) -> str:
    letters = []
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _quote_sheet_name(sheet: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_]+", sheet or ""):
        return sheet
    return "'" + sheet.replace("'", "''") + "'"


def _format_a1_range(a1_range: str) -> str:
    """Quote sheet title when needed (spaces, hyphens, etc.) for Google Sheets API."""
    if "!" not in a1_range:
        return a1_range
    sheet, cell = a1_range.rsplit("!", 1)
    sheet = sheet.strip()
    if sheet.startswith("'") and sheet.endswith("'"):
        return a1_range
    return f"{_quote_sheet_name(sheet)}!{cell}"


def _parse_sheet_rectangular_range(sh_name: str):
    """
    Parse 'Sheet'!C1:D10 into (sheet_title, col_start_idx, row_start, col_end_idx, row_end).
    sheet_title is unquoted. Returns None if not a single rectangular A1 block.
    """
    if "!" not in sh_name:
        return None
    sheet_raw, cell = sh_name.rsplit("!", 1)
    sheet_raw = sheet_raw.strip()
    if sheet_raw.startswith("'") and sheet_raw.endswith("'"):
        sheet = sheet_raw[1:-1].replace("''", "'")
    else:
        sheet = sheet_raw
    m = _CELL_RANGE_RE.match(cell.strip())
    if not m:
        return None
    c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
    i1, i2 = _col_letters_to_index(c1), _col_letters_to_index(c2)
    if i1 > i2 or r1 > r2:
        return None
    return sheet, i1, r1, i2, r2


class GmailEntry:
    _REFRESH_SKEW = timedelta(minutes=5)

    def __init__(self, scopes, sh_name, ranges, client_secrets_path):
        self.scopes = scopes
        self.sh_name = sh_name
        self.ranges = ranges
        self.client_secrets_path = client_secrets_path
        # Define o caminho do token na mesma pasta das credenciais
        dir_name = os.path.dirname(client_secrets_path)
        self.token_path = os.path.join(dir_name, 'token.json')
        self._scopes = ['https://www.googleapis.com/auth/spreadsheets']
        self._creds = None
        try:
            self.ensure_fresh_credentials(force=True)
        except Exception as e:
            print(
                f"Aviso: refresh inicial do token Google falhou ({e}). "
                "Seguindo; get_sheets tentará de novo com retries."
            )

    def _save_credentials(self, creds):
        with open(self.token_path, 'w') as token:
            token.write(creds.to_json())
        self._creds = creds

    def _load_credentials(self):
        if self._creds is not None:
            return self._creds
        if not os.path.exists(self.token_path):
            return None
        try:
            creds = Credentials.from_authorized_user_file(self.token_path, self._scopes)
        except Exception:
            return None
        self._creds = creds
        return creds

    def _refresh_with_retry(self, creds, retries=5):
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                creds.refresh(Request())
                self._save_credentials(creds)
                return creds
            except Exception as e:
                last_error = e
                if attempt < retries:
                    wait = 5 * attempt
                    print(
                        f"refresh token tentativa {attempt}/{retries} falhou: {e}. "
                        f"Tentando novamente em {wait}s..."
                    )
                    time.sleep(wait)
        raise last_error

    @staticmethod
    def _expiry_utc(creds):
        if not creds or not creds.expiry:
            return None
        expiry = creds.expiry
        if expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry.astimezone(timezone.utc)

    def _expires_within(self, creds, skew=None):
        skew = skew if skew is not None else self._REFRESH_SKEW
        expiry = self._expiry_utc(creds)
        if expiry is None:
            return False
        return expiry <= datetime.now(timezone.utc) + skew

    def ensure_fresh_credentials(self, force=True):
        """Renova o token OAuth cedo (útil antes de jobs longos)."""
        creds = self._load_credentials()
        if creds and creds.refresh_token and (force or not creds.valid or self._expires_within(creds)):
            print("Renovando token Google Sheets...")
            return self._refresh_with_retry(creds)
        if creds and creds.valid:
            return creds
        return self._get_credentials()

    def _get_credentials(self):
        creds = self._load_credentials()

        if creds and creds.valid and not self._expires_within(creds):
            return creds

        if creds and creds.refresh_token and (not creds.valid or self._expires_within(creds)):
            return self._refresh_with_retry(creds)

        flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_path, self._scopes)
        creds = flow.run_local_server(port=0)
        self._save_credentials(creds)
        return creds

    @staticmethod
    def _sheet_values_to_dataframe(values):
        """Monta DataFrame a partir de ROWS; preenche só o fim da linha (células vazias omitidas no fim)."""
        if not values:
            return pd.DataFrame()
        header = ["" if h is None else str(h).strip() for h in values[0]]
        n = len(header)
        rows = []
        for raw in values[1:]:
            row = list(raw)
            if len(row) < n:
                row.extend([None] * (n - len(row)))
            elif len(row) > n:
                row = row[:n]
            rows.append(row)
        return pd.DataFrame(rows, columns=header)

    @staticmethod
    def _batch_get_rectangular_to_dataframe(sheet_title, spreadsheet_id, i1, r1, i2, r2, sheet_api):
        """
        Lê B4:W500 pedindo cada coluna (B4:B500, C4:C500, ...). Assim a coluna L vazia no meio
        não 'some' e desloca Rota atualizada com movings / Status (problema do modo ROWS da API).
        """
        qs = _quote_sheet_name(sheet_title)
        ncols = i2 - i1 + 1
        nrows = r2 - r1 + 1
        ranges = [
            f"{qs}!{_index_to_col_letters(ci)}{r1}:{_index_to_col_letters(ci)}{r2}"
            for ci in range(i1, i2 + 1)
        ]
        batch = sheet_api.values().batchGet(
            spreadsheetId=spreadsheet_id, ranges=ranges, majorDimension="ROWS"
        ).execute()
        value_ranges = batch.get("valueRanges") or []
        matrix = [[None] * ncols for _ in range(nrows)]
        for col_idx, vr in enumerate(value_ranges):
            if col_idx >= ncols:
                break
            vals = vr.get("values") or []
            col_cells = []
            for row in vals:
                if not row:
                    col_cells.append(None)
                else:
                    col_cells.append(row[0])
            if len(col_cells) < nrows:
                col_cells.extend([None] * (nrows - len(col_cells)))
            elif len(col_cells) > nrows:
                col_cells = col_cells[:nrows]
            for ri, v in enumerate(col_cells):
                matrix[ri][col_idx] = v
        if not matrix:
            return pd.DataFrame()
        header = ["" if h is None else str(h).strip() for h in matrix[0]]
        body = matrix[1:]
        return pd.DataFrame(body, columns=header)

    def get_sheets(self, scopes, sh_name, timeout=120, retries=3):
        start_time = time.time()

        SAMPLE_SPREADSHEET_ID = f'{scopes}'
        SAMPLE_RANGE_NAME = f'{sh_name}'

        for attempt in range(1, retries + 1):
            try:
                creds = self._get_credentials()
                # Set default socket timeout for this request
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(timeout)
                try:
                    service = build('sheets', 'v4', credentials=creds)
                    sheet = service.spreadsheets()
                    parsed = _parse_sheet_rectangular_range(SAMPLE_RANGE_NAME)
                    use_batch = (
                        parsed is not None
                        and (parsed[3] - parsed[1] + 1) <= 80
                        and (parsed[4] - parsed[2] + 1) <= 50000
                    )
                    if use_batch:
                        sheet_title, i1, r1, i2, r2 = parsed
                        df_result = self._batch_get_rectangular_to_dataframe(
                            sheet_title, SAMPLE_SPREADSHEET_ID, i1, r1, i2, r2, sheet
                        )
                    else:
                        result = sheet.values().get(
                            spreadsheetId=SAMPLE_SPREADSHEET_ID,
                            range=SAMPLE_RANGE_NAME,
                            majorDimension="ROWS",
                        ).execute()
                        raw_values = result.get("values") or []
                        df_result = self._sheet_values_to_dataframe(raw_values)
                finally:
                    socket.setdefaulttimeout(old_timeout)

                end_time = time.time()
                print("running time:", end_time - start_time)
                return df_result
            except (socket.timeout, OSError, Exception) as e:
                if attempt < retries:
                    wait = 5 * attempt
                    print(f"get_sheets tentativa {attempt}/{retries} falhou: {e}. Tentando novamente em {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def print_in_sheets(self, scopes, sh_name, df, print_columns=True):
        creds = self._get_credentials()

        service = build('sheets', 'v4', credentials=creds)
        sh_range = _format_a1_range(sh_name)

        if print_columns:
            response_date = service.spreadsheets().values().update(
                spreadsheetId=scopes,
                valueInputOption='RAW',
                range=sh_range,
                body=dict(
                    majorDimension='ROWS',
                    values=[df.columns.tolist()] + df.values.tolist()),
            ).execute()
            print('Sheet successfully updated')
        else:
            response_date = service.spreadsheets().values().update(
                spreadsheetId=scopes,
                valueInputOption='RAW',
                range=sh_range,
                body=dict(
                    majorDimension='ROWS',
                    values=df.values.tolist()),
            ).execute()
            print('Sheet successfully updated')



    def clean_whole_sheet(self, sheet_id, sheet_name):
        creds = self._get_credentials()

        service = build('sheets', 'v4', credentials=creds)
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=sheet_name,
        ).execute()
        print(f'Sheet {sheet_name} successfully cleared')


    def clean_specific_range(self, sheet_id, sheet_name, range_to_clear):
        creds = self._get_credentials()

        service = build('sheets', 'v4', credentials=creds)

        # Clear the specified range
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=_format_a1_range(f'{sheet_name}!{range_to_clear}'),
        ).execute()
        print(f'Range {range_to_clear} in sheet {sheet_name} successfully cleared')

    def clean_in_sheets(self, scopes, sh_name):
        creds = self._get_credentials()

        service = build('sheets', 'v4', credentials=creds)

        
        spreadsheet_id = scopes
        sheet_name = sh_name

        # Clear the sheet
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=sheet_name,
        ).execute()
        print(f'Sheet {sheet_name} successfully cleared')

    def print_in_sheets_bach(self, scopes, sh_name, df, print_columns=True):
        creds = self._get_credentials()

        service = build('sheets', 'v4', credentials=creds)

        if print_columns:
            response_date = service.spreadsheets().values().update(
                spreadsheetId=scopes,
                valueInputOption='RAW',
                range=sh_name,
                body=dict(
                    majorDimension='ROWS',
                    values=[df.columns.tolist()] + df.values.tolist()),
            ).execute()
            print('Sheet successfully updated')
        else:
            response_date = service.spreadsheets().values().update(
                spreadsheetId=scopes,
                valueInputOption='RAW',
                range=sh_name,
                body=dict(
                    majorDimension='ROWS',
                    values=df.values.tolist()),
            ).execute()
            print('Sheet successfully updated')

    def get_last_empty_row(self, spreadsheet_id, sheet_name, column, timeout=120, retries=3):
        for attempt in range(1, retries + 1):
            try:
                creds = self._get_credentials()
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(timeout)
                try:
                    service = build('sheets', 'v4', credentials=creds)
                    range_name = f"{sheet_name}!{column}:{column}"
                    result = service.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=range_name
                    ).execute()
                finally:
                    socket.setdefaulttimeout(old_timeout)
                values = result.get('values', [])
                last_empty_row = len(values) + 1
                return last_empty_row
            except (socket.timeout, OSError, Exception) as e:
                if attempt < retries:
                    wait = 5 * attempt
                    print(f"get_last_empty_row tentativa {attempt}/{retries} falhou: {e}. Tentando novamente em {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def print_values_in_sheets(self, spreadsheet_id, sheet_name, df):
        creds = self._get_credentials()
        service = build('sheets', 'v4', credentials=creds)
        response = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            valueInputOption='RAW',
            range=sheet_name,
            body={
                'majorDimension': 'ROWS',
                'values': df.values.tolist()
            }
        ).execute()
        print('Values (without headers) successfully updated')