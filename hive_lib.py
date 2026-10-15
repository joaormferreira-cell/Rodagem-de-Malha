import os
import requests
import json
import logging
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
from pyhive import presto
import pandas as pd
from dotenv import load_dotenv

from dataservice.body import Expressions, Body
from dataservice.query_configuration import QueryConfiguration
from dataservice.sdk import Client

# Garante o carregamento do .env a partir do diretório raiz onde este arquivo está
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

def get_df_demand(query):
    hadoop_account = os.environ.get('HADOOP_USER_NAME')
    hadoop_pwd = os.environ.get('HADOOP_USER_RPCPASSWORD')

    ## Different IDCs have different clusters...............................
    ## https://confluence.shopee.io/display/DI/%5BPresto%5D+Accessing+Presto+Clusters
    ## Recommended to use External type host:
    ##        SG: presto-secure.data-infra.shopee.io
    ##   US East: us.presto-secure.data-infra.shopee.io
    presto_host = "presto-secure.data-infra.shopee.io"
    presto_port = 443
    protocol = 'https'

    ## Replace "your_own_project_adhoc_queue" with your own project queue name. Go to RAM to get the queue name.
    presto_queue = 'brbi-adhoc'

    ## SG or USEast
    idc_region = 'SG'
    source = f'(49)-({presto_queue})-({hadoop_account})-(jdbc)-({hadoop_account})-({idc_region})'
 
    ## This is necessary
    os.environ["DATABASE_URL"] = f"presto://{hadoop_account}:{hadoop_pwd}@{presto_host}:{presto_port}/hive?protocol={protocol}&source={source}"
    print('Trying to get demand table...')
    db_conn = presto.connect('presto-secure.data-infra.shopee.io', port='443', protocol='https',\
                          source=f'(49)-(brbi-adhoc)-({hadoop_account})-(jdbc)-({hadoop_account})-(SG)',\
                          username=hadoop_account, password=hadoop_pwd, schema='shopee')
    
    
    
    # db_conn = presto.connect('us.presto-secure.data-infra.shopee.io', port='443', protocol='https',\
    #                       source=f'(50)-(brbi-adhoc)-({hadoop_account})-(jdbc)-({hadoop_account})-(USEast)',\
    #                       username=hadoop_account, password=hadoop_pwd, schema='shopee')
    
    cursor = db_conn.cursor()
    cursor.execute(query)
    
    print('Query sucessful, transforming to dataframe...')
    columns = [desc[0] for desc in cursor.description]
    print("Fields:", columns)
    results = cursor.fetchall()
    df = pd.DataFrame(results, columns=columns)
    print('Done.')
    return df

# Function to write data from DataFrame to Data HUB API
def insert_df_into_hive(df, api_endpoint, ingestion_token):
    print(f"Preparando {len(df)} linhas para upload...")
    csv_data = df.to_csv(encoding='utf-8', index=False)
    
    # Encoder para o upload
    encoder = MultipartEncoder(fields={'file': ('file.csv', csv_data.encode('utf-8'), 'text/plain')})
    
    # Função de callback para mostrar o progresso
    def callback(monitor):
        # Calcula a porcentagem
        progress = (monitor.bytes_read / monitor.len) * 100
        # Imprime o progresso na mesma linha (usando \r)
        print(f"\rUpload progress: {progress:.2f}% ({monitor.bytes_read}/{monitor.len} bytes)", end="", flush=True)

    # Monitor que envolve o encoder
    monitor = MultipartEncoderMonitor(encoder, callback)
    
    headers = {'data-ingestion-token': ingestion_token, 'Content-Type': monitor.content_type}
    
    print("Iniciando upload para o DataHub...")
    try:
        response = requests.request('POST', api_endpoint, headers=headers, data=monitor)
        print("\nUpload concluído!")
        print(response.text)
    except Exception as e:
        print(f"\nErro durante o upload: {e}")

# Function to fetch data from Shopee Data Service API (BWT)
def get_df_from_dataservice(api_abbr="brbi_opslgc.get_bwt_network_jards", version="adna3p6n2831dkgh", app_key=None, app_secret=None):
    if not app_key:
        app_key = os.environ.get('APP_KEY')
    if not app_secret:
        app_secret = os.environ.get('APP_SECRET')
    
    if not app_key or not app_secret:
        raise RuntimeError("APP_KEY or APP_SECRET not found in environment variables.")

    timeout_raw = os.environ.get("DATASERVICE_TIMEOUT_SECONDS", "60")
    try:
        request_timeout = max(5, int(timeout_raw))
    except ValueError:
        logging.warning(
            "Invalid DATASERVICE_TIMEOUT_SECONDS='%s'. Falling back to 60 seconds.",
            timeout_raw,
        )
        request_timeout = 60

    print(f"Connecting to Data Service API: {api_abbr} ({version}) with timeout={request_timeout}s...")
    
    client = Client() \
        .create() \
        .appKey(app_key) \
        .appSecret(app_secret) \
        .scope([api_abbr]) \
        .timeout(request_timeout) \
        .systemName("Python_BWT_Automation") \
        .endUser("jards.silva@shopee.com") \
        .refresh()
        
    expressions = Expressions().getExpressions()
    body = Body(expressions=expressions).__dict__

    queryConfig = QueryConfiguration(
        apiName=api_abbr,
        version=version,
        enableCache=True,
        queryPattern=QueryConfiguration.QueryPattern.OLAP,
        requestBody=body,
        prestoQueueName="brbi-scheduled",
        network=QueryConfiguration.Env.INTRANET
    )
    
    results_generator = client.callWithQueryConfig(queryConfig)
    
    all_rows = []
    print("Fetching results from API...")
    try:
        for page in results_generator:
            # results_generator yields lists of results (each result have 'values' dict)
            if isinstance(page, list):
                for item in page:
                    all_rows.append(item['values'])
            else:
                # For small results it might just be the result itself
                if 'values' in page:
                    all_rows.append(page['values'])
            
            # Mostra o progresso atualizado na mesma linha
            print(f"\rFetched {len(all_rows)} rows...", end="", flush=True)
    except requests.exceptions.Timeout as exc:
        logging.error(
            "Timeout while fetching DataService API '%s' with timeout=%ss.",
            api_abbr,
            request_timeout,
        )
        raise RuntimeError(
            f"Timeout fetching DataService API '{api_abbr}'. "
            f"Try increasing DATASERVICE_TIMEOUT_SECONDS (current: {request_timeout})."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        logging.error(
            "Connection error while fetching DataService API '%s' with timeout=%ss.",
            api_abbr,
            request_timeout,
        )
        raise RuntimeError(
            f"Connection error fetching DataService API '{api_abbr}'. "
            f"Try increasing DATASERVICE_TIMEOUT_SECONDS (current: {request_timeout}) and retry."
        ) from exc
    except RuntimeError as exc:
        # dataservice SDK wraps read timeout into RuntimeError in resilience layer
        if "Read timeout" in str(exc):
            logging.error(
                "Read timeout from DataService SDK for API '%s' with timeout=%ss.",
                api_abbr,
                request_timeout,
            )
            raise RuntimeError(
                f"Read timeout fetching DataService API '{api_abbr}'. "
                f"Try increasing DATASERVICE_TIMEOUT_SECONDS (current: {request_timeout})."
            ) from exc
        raise
            
    print("\nFetch complete. Converting to DataFrame...")
    df = pd.DataFrame(all_rows)
    print(f"Total rows fetched: {len(df)}")
    
    if len(df) == 0:
        return df

    # Mapping to correct column names expected by scripts
    # Note: DS API returns low_case with underscores instead of original headers
    cols_rename = {
        'ado': 'ADO',
        'e2e_path': 'E2E Path',
        'fmh': 'FMH',
        'fmh_hub': 'FMH-HUB',
        'fmh_soc': 'FMH-SOC',
        'lmh': 'LMH',
        'period_start': 'period_start',
        'soc_hub': 'SOC-HUB',
        'soc_xpt': 'SOC-XPT',
        'soc1': 'SOC1',
        'soc1_soc2': 'SOC1-SOC2',
        'soc2': 'SOC2',
        'soc2_soc3': 'SOC2-SOC3',
        'soc3': 'SOC3',
        'soc3_soc4': 'SOC3-SOC4',
        'soc4': 'SOC4',
        'soc4_hub': 'SOC4-HUB',
        'hub_xpt': 'HUB-XPT',
        'xpt': 'XPT',
        'erro': 'ERRO',
        'origin': 'ORIGIN',
        'destination': 'DESTINATION'
    }
    
    # Handle the ones that already have - in the name if they come through normally
    # API tends to replace - with _
    df = df.rename(columns=cols_rename)
    
    # Alias DESTINATION to DEST if needed by bwt_calculator
    if 'DESTINATION' in df.columns and 'DEST' not in df.columns:
        df['DEST'] = df['DESTINATION']
    
    # Fill NaN with empty strings for station columns to avoid 'float is not subscriptable' errors
    cols_to_fix = ['FMH', 'SOC1', 'SOC2', 'SOC3', 'SOC4', 'LMH', 'XPT', 'E2E Path', 'ERRO']
    for col in cols_to_fix:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    # Ensure ADO is numeric
    if 'ADO' in df.columns:
        df['ADO'] = pd.to_numeric(df['ADO'], errors='coerce').fillna(0)
    
    # Ensure period_start is string in YYYY-MM-DD format (as expected by original scripts)
    if 'period_start' in df.columns:
        df['period_start'] = pd.to_datetime(df['period_start']).dt.strftime('%Y-%m-%d')

    return df


def get_df_demand_params(api_abbr, version, br_grass_datetime, period_start_from, period_start_to,
                          app_key=None, app_secret=None, system_name="Python_BWT_Automation",
                          end_user="jards.silva@shopee.com"):
    """
    Chama uma Data Service API em "Code Mode" (Data Suite) que aceita
    parâmetros dinâmicos via ${param} -- usado pelo Network Input do
    Portal BWT para automatizar br_grass_datetime e o range de period_start
    sem precisar de acesso JDBC direto ao Presto (bloqueado pela Shopee
    para novos usuários desde 16/10/2025).

    A API precisa ter sido criada no Data Suite com 3 parâmetros String:
    br_grass_datetime, period_start_from, period_start_to (ver README do
    portal_bwt para o SQL usado). Retorna o dado BRUTO (orders por mês,
    sem dividir por dias úteis) -- a divisão por business_days é feita
    depois, em Python, com base na tabela business_days_per_month.

    Nota: APIs Code Mode parametrizadas (ex. forecast_pi_demand_monthly) não
    aceitam prestoQueueName no QueryConfiguration -- o gateway retorna 404
    se esse campo for enviado. APIs sem parâmetros usam get_df_from_dataservice.
    """
    from dataservice.body import Expressions, Body
    from dataservice.query_configuration import QueryConfiguration
    from dataservice.sdk import Client

    if not app_key:
        app_key = os.environ.get('APP_KEY')
    if not app_secret:
        app_secret = os.environ.get('APP_SECRET')

    if not app_key or not app_secret:
        raise RuntimeError(
            "APP_KEY or APP_SECRET not found in environment variables."
        )

    print(f"Connecting to Data Service API (parametrizada): {api_abbr} ({version})...")

    client = Client() \
        .create() \
        .appKey(app_key) \
        .appSecret(app_secret) \
        .scope([api_abbr]) \
        .systemName(system_name) \
        .endUser(end_user) \
        .refresh()

    expressions = Expressions() \
        .addExpression(parameterName="br_grass_datetime", value=br_grass_datetime) \
        .addExpression(parameterName="period_start_from", value=period_start_from) \
        .addExpression(parameterName="period_start_to", value=period_start_to) \
        .getExpressions()
    body = Body(expressions=expressions).__dict__

    queryConfig = QueryConfiguration(
        apiName=api_abbr,
        version=version,
        enableCache=True,
        queryPattern=QueryConfiguration.QueryPattern.OLAP,
        requestBody=body,
        network=QueryConfiguration.Env.INTRANET
    )

    all_rows = []
    print("Fetching results from API (parametrizada)...")
    try:
        for shard in client.callWithQueryConfig(queryConfig):
            for row in shard:
                # Alguns retornos da SDK vêm como {'values': {...}}, outros já
                # como o dict de colunas direto -- trata os dois formatos.
                if isinstance(row, dict) and 'values' in row:
                    all_rows.append(row['values'])
                else:
                    all_rows.append(row)
    except RuntimeError as exc:
        msg = str(exc)
        if "path not register on gateway" in msg.lower() or "404" in msg:
            raise RuntimeError(
                f"Data Service gateway não reconhece '{api_abbr}' version '{version}'. "
                f"Verifique no Data Suite: (1) API publicada com esse nome exato "
                f"(opslgc com L, não ops1gc com 1); (2) version ID da aba Published; "
                f"(3) app BWT_App autorizado para essa API. "
                f"Rode: python portal_bwt/scripts/diagnose_demand_api.py. "
                f"Detalhe original: {msg}"
            ) from exc
        raise

    print(f"\nFetch complete. {len(all_rows)} linha(s) recebida(s). Convertendo para DataFrame...")
    df = pd.DataFrame(all_rows)
    return df