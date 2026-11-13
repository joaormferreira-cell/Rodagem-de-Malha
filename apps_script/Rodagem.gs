/**
 * Rodagem de Malha: botão para gravar o resultado na planilha "2. BWT Output by step".
 * Instalar: Extensões > Apps Script > colar este arquivo inteiro > Salvar > recarregar a planilha.
 * Usar: menu "Rodagem" > "Atualizar resultado" > escolher os CSV da pasta saida\planilha.
 *
 * Modo SUBSTITUIR MÊS: os meses que vêm no CSV saem da aba e entram os novos; os outros meses ficam.
 * Roda com o login de quem clica (não precisa de chave/credencial).
 */

// regravarCabecalho: nas abas raw_* o cabeçalho antigo estava fora da ordem das colunas (o Summary lia a
// coluna vizinha); na Network o cabeçalho já está certo e a célula A10 ("Bwt output") fica como está.
var ABAS = {
  'Network BWT output': {linhaCabecalho: 10, regravarCabecalho: false},
  'raw_bwt': {linhaCabecalho: 2, regravarCabecalho: true},
  'raw_data_1st_SOC': {linhaCabecalho: 2, regravarCabecalho: true}
};

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Rodagem')
    .addItem('Atualizar resultado', 'abrirJanela')
    .addToUi();
}

function abrirJanela() {
  var html = HtmlService.createHtmlOutput(JANELA_HTML).setWidth(520).setHeight(420);
  SpreadsheetApp.getUi().showModalDialog(html, 'Rodagem de Malha: atualizar resultado');
}

/** Tira da aba as linhas dos meses informados e grava o cabeçalho certo. Devolve quantas linhas saíram. */
function prepararAba(nomeAba, cabecalho, meses) {
  var aba = SpreadsheetApp.getActive().getSheetByName(nomeAba);
  if (!aba) throw new Error('Aba não encontrada: ' + nomeAba);
  var cab = ABAS[nomeAba].linhaCabecalho;
  if (ABAS[nomeAba].regravarCabecalho) aba.getRange(cab, 1, 1, cabecalho.length).setValues([cabecalho]);

  var ultima = aba.getLastRow();
  if (ultima <= cab) return 0;
  var colA = aba.getRange(cab + 1, 1, ultima - cab, 1).getDisplayValues();
  var tirar = {};
  meses.forEach(function (m) { tirar[m] = true; });
  // apaga de baixo para cima, em blocos seguidos (rápido mesmo com 200 mil linhas)
  var removidas = 0, i = colA.length - 1;
  while (i >= 0) {
    if (tirar[String(colA[i][0]).substring(0, 10)]) {
      var fim = i;
      while (i >= 0 && tirar[String(colA[i][0]).substring(0, 10)]) i--;
      aba.deleteRows(cab + 1 + i + 1, fim - i);
      removidas += fim - i;
    } else {
      i--;
    }
  }
  return removidas;
}

/** Grava um lote de linhas no fim da aba. A 1ª coluna (mês) fica como texto, como o Summary espera. */
function gravarLote(nomeAba, linhas) {
  var aba = SpreadsheetApp.getActive().getSheetByName(nomeAba);
  var inicio = Math.max(aba.getLastRow(), ABAS[nomeAba].linhaCabecalho) + 1;
  var precisa = inicio + linhas.length - 1 - aba.getMaxRows();
  if (precisa > 0) aba.insertRowsAfter(aba.getMaxRows(), precisa);
  var valores = linhas.map(function (l) {
    return l.map(function (v, j) {
      if (j === 0) return "'" + v;                                   // mês como texto
      return /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(v) ? Number(v) : v;
    });
  });
  aba.getRange(inicio, 1, valores.length, valores[0].length).setValues(valores);
  return valores.length;
}

var JANELA_HTML = '\
<style>body{font-family:Arial;font-size:13px} .l{margin:8px 0} #log{white-space:pre-wrap;background:#f4f4f4;padding:6px;height:150px;overflow:auto}\
button{background:#EE4D2D;color:#fff;border:0;padding:8px 14px;cursor:pointer}</style>\
<div>Escolha os arquivos da pasta <b>saida\\planilha</b> (pode escolher só alguns):</div>\
<div class="l">Network BWT output: <input type="file" id="f1" accept=".csv"></div>\
<div class="l">raw_bwt: <input type="file" id="f2" accept=".csv"></div>\
<div class="l">raw_data_1st_SOC: <input type="file" id="f3" accept=".csv"></div>\
<button onclick="comecar()">Gravar</button>\
<div id="log" class="l"></div>\
<script>\
var LOTE=4000;\
function log(t){var e=document.getElementById("log");e.textContent+=t+"\\n";e.scrollTop=e.scrollHeight;}\
function lerCsv(texto){var linhas=[],campo="",linha=[],aspas=false;\
 for(var i=0;i<texto.length;i++){var c=texto[i];\
  if(aspas){if(c==="\\""){if(texto[i+1]==="\\""){campo+="\\"";i++;}else aspas=false;}else campo+=c;}\
  else if(c==="\\""){aspas=true;}else if(c===","){linha.push(campo);campo="";}\
  else if(c==="\\n"){linha.push(campo.replace(/\\r$/,""));linhas.push(linha);linha=[];campo="";}else campo+=c;}\
 if(campo!==""||linha.length){linha.push(campo);linhas.push(linha);}return linhas;}\
function chamar(fn,args){return new Promise(function(ok,erro){var r=google.script.run.withSuccessHandler(ok).withFailureHandler(erro);r[fn].apply(r,args);});}\
function lerArquivo(f){return new Promise(function(ok){var r=new FileReader();r.onload=function(){ok(r.result);};r.readAsText(f,"UTF-8");});}\
async function gravarAba(nome,arquivo){\
 var linhas=lerCsv(await lerArquivo(arquivo));var cab=linhas.shift();\
 var meses={};linhas.forEach(function(l){meses[String(l[0]).substring(0,10)]=1;});meses=Object.keys(meses).sort();\
 log(nome+": "+linhas.length+" linhas, meses "+meses.join(", "));\
 var tiradas=await chamar("prepararAba",[nome,cab,meses]);log("  saíram "+tiradas+" linhas antigas desses meses");\
 for(var i=0;i<linhas.length;i+=LOTE){await chamar("gravarLote",[nome,linhas.slice(i,i+LOTE)]);\
  log("  gravadas "+Math.min(i+LOTE,linhas.length)+" de "+linhas.length);}\
 log("  OK");}\
async function comecar(){try{\
 var mapa=[["Network BWT output","f1"],["raw_bwt","f2"],["raw_data_1st_SOC","f3"]];\
 for(var k=0;k<mapa.length;k++){var f=document.getElementById(mapa[k][1]).files[0];if(f)await gravarAba(mapa[k][0],f);}\
 log("\\nPRONTO. Pode fechar esta janela.");}catch(e){log("ERRO: "+e.message);}}\
</script>';
