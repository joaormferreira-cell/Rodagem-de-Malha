# Botão "Rodagem → Atualizar resultado" (Google Sheets)

Grava o resultado da ferramenta na planilha "2. BWT Output by step" sem chave de acesso:
roda com o login de quem clica.

## Instalar (uma vez por planilha)
1. Abra a planilha (comece pela **cópia de TESTE**).
2. Menu **Extensões → Apps Script**.
3. Apague o que estiver no editor e cole **todo** o conteúdo de `apps_script/Rodagem.gs`.
4. Clique no disquete (**Salvar**) e feche a aba do Apps Script.
5. Recarregue a planilha (F5). Aparece o menu **Rodagem** no alto.
6. Na 1ª vez, o Google pede autorização: **Continuar → escolher sua conta → Avançado → Acessar (não seguro) → Permitir**.
   (O aviso aparece porque o script é seu e não foi publicado; ele só mexe nesta planilha.)

## Usar (toda rodagem)
1. Rode a ferramenta (`RODAR.bat`). Ela cria a pasta `saida\planilha` com 3 arquivos.
2. Na planilha: **Rodagem → Atualizar resultado**.
3. Escolha os 3 arquivos e clique em **Gravar**. Acompanhe o andamento na janela (a aba grande leva alguns minutos).

## O que ele faz
- **Substitui o mês:** apaga da aba as linhas dos meses que estão no arquivo e grava as novas. Os outros meses ficam.
  Rodar duas vezes não duplica.
- O mês é gravado como **texto** (o Summary compara texto).
- Nas abas `raw_bwt` e `raw_data_1st_SOC` regrava o cabeçalho na ordem certa (o antigo estava trocado).
