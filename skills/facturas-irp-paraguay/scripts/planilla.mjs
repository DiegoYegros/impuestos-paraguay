import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('uso: node planilla.mjs libro.json salida.xlsx');
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const wb = Workbook.create();
const safe = value => typeof value === 'string' && /^[\s]*[=+@-]/.test(value) ? `'${value}` : value;
const columns = ['id', 'fecha', 'emisor', 'número', 'concepto', 'total Gs', 'deducible Gs',
  'estado', 'motivo / pendiente', 'carga', 'original', 'norma'];
const rows = data.documentos.map(d => [d.id,
  d.fecha && /^\d{4}-\d{2}-\d{2}$/.test(d.fecha) ? new Date(`${d.fecha}T12:00:00Z`) : d.fecha,
  d.emisor || d.ruc_emisor, d.numero, d.concepto, d.total_gs, d.deducible_gs,
  d.estado, [d.motivo, ...(d.pendientes || [])].filter(Boolean).join(' · '), d.ruta_carga,
  (d.fuentes || []).map(f => `${f.archivo} ${f.ubicacion || ''}`).join(' · '),
  `${d.articulo || ''} ${d.norma_url || ''}`].map(v => safe(v ?? null)));

function tableSheet(name, title, content) {
  const sh = wb.worksheets.add(name);
  sh.showGridLines = false;
  sh.getRange('A1:H2').merge();
  sh.getRange('A1').values = [[title]];
  sh.getRange('A1:L2').format.fill = '#153E4C';
  sh.getRange('A1:L2').format.font = {name: 'Arial', size: 18, bold: true, color: '#FFFFFF'};
  sh.getRange('A3:H3').merge();
  sh.getRange('A3').values = [['borrador · vacíos = pendiente de determinar · importes en guaraníes']];
  sh.getRange('A5:L5').values = [columns];
  if (content.length) sh.getRange(`A6:L${content.length + 5}`).values = content;
  const end = Math.max(6, content.length + 5);
  sh.getRange(`A5:L${end}`).format.font = {name: 'Arial', size: 10};
  sh.getRange(`A5:L${end}`).format.rowHeight = 48;
  sh.getRange(`A5:L${end}`).format.wrapText = true;
  sh.getRange(`A5:L${end}`).format.columnWidth = 18;
  sh.getRange(`E5:E${end}`).format.columnWidth = 30;
  sh.getRange(`I5:I${end}`).format.columnWidth = 45;
  sh.getRange(`K5:L${end}`).format.columnWidth = 42;
  sh.getRange(`F6:G${end}`).setNumberFormat('#,##0;[Red](#,##0);0');
  sh.getRange(`B6:B${end}`).setNumberFormat('dd/mm/yyyy');
  sh.getRange('A5:L5').format.fill = '#D9E8EA';
  sh.getRange('A5:L5').format.font = {bold: true, color: '#153E4C'};
  sh.tables.add(`A5:L${end}`, true, `${name}Tabla`);
  sh.freezePanes.freezeRows(5);
  sh.freezePanes.freezeColumns(2);
  content.forEach((r, i) => {
    sh.getRange(`H${i + 6}`).format.fill = r[7] === 'deducible' ? '#D9EDDF' :
      r[7] === 'revisar' ? '#FFF0C2' : '#E6E6E6';
  });
  return sh;
}

tableSheet('Facturas', `facturas · IRP ${data.perfil.ejercicio}`, rows);
tableSheet('Pendientes', 'pendientes de revisión', rows.filter(r => r[7] === 'revisar'));
const loadFields = ['id', 'ruc_emisor', 'ruc_destinatario', 'fecha', 'tipo', 'origen',
  'timbrado', 'numero', 'cdc', 'moneda', 'condicion', 'total_gs', 'gravado_10_gs',
  'gravado_5_gs', 'exento_gs', 'imputaciones'];
const load = wb.worksheets.add('Carga');
load.getRange('A1:P1').values = [loadFields];
if (data.documentos.length) {
  load.getRange(`A2:P${data.documentos.length + 1}`).values = data.documentos.map(d =>
    loadFields.map(k => safe(k === 'imputaciones' && Array.isArray(d[k]) ?
      [...d[k]].sort().join(',') : d[k] ?? null)));
}
load.getRange(`A1:P${Math.max(2, data.documentos.length + 1)}`).format.columnWidth = 22;
load.getRange('A1:P1').format.fill = '#D9E8EA';
load.getRange('A1:P1').format.font = {bold: true};
load.getRange(`L2:O${Math.max(2, data.documentos.length + 1)}`).setNumberFormat('#,##0');
load.freezePanes.freezeRows(1);
const summary = wb.worksheets.add('Resumen');
summary.showGridLines = false;
summary.getRange('A1:B2').merge();
summary.getRange('A1').values = [['resumen del libro']];
summary.getRange('A1:B2').format.fill = '#153E4C';
summary.getRange('A1:B2').format.font = {size: 18, color: '#FFFFFF', bold: true};
summary.getRange('A4:B9').values = [
  ['ejercicio', data.perfil.ejercicio], ['deducible identificado Gs', null],
  ['facturas deducibles', null], ['pendientes', null], ['duplicados', null],
  ['no deducibles', null]];
const last = Math.max(6, rows.length + 5);
summary.getRange('B5:B9').formulas = [
  [`=SUM(Facturas!G6:G${last})`],
  ...['deducible', 'revisar', 'duplicado', 'no_deducible'].map(s =>
    [`=COUNTIF(Facturas!H6:H${last},"${s}")`])];
summary.getRange('B5').setNumberFormat('#,##0');
summary.getRange('A11:B13').merge();
summary.getRange('A11').values = [[data.resumen.alcance]];
summary.getRange('A11:B13').format.wrapText = true;
summary.getRange('A15:B17').merge();
summary.getRange('A15').values = [[safe(`fuentes de vigencia: ${JSON.stringify(data.perfil.fuentes_vigencia || [])}`)]];
summary.getRange('A15:B17').format.wrapText = true;
summary.getRange('A4:B17').format.rowHeight = 26;
summary.getRange('A1:A17').format.columnWidth = 40;
summary.getRange('B1:B17').format.columnWidth = 30;
wb.recalculate();
const actual = summary.getRange('B5').values[0][0];
if (Number(actual) !== data.resumen.deducible_identificado_gs) {
  throw new Error(`total XLSX ${actual} no coincide con libro ${data.resumen.deducible_identificado_gs}`);
}
await fs.mkdir(path.dirname(path.resolve(output)), {recursive: true});
const audit = await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',
  options: {useRegex: true, maxResults: 100}});
await fs.writeFile(`${output}.verificacion.json`, JSON.stringify(audit, null, 2));
for (const [name, range] of [['Facturas', 'A1:H10'], ['Pendientes', 'A1:H10'], ['Carga', 'A1:H6'], ['Resumen', 'A1:B17']]) {
  const preview = await wb.render({sheetName: name, range, scale: 1, format: 'png'});
  await fs.writeFile(`${output}.${name}.png`, new Uint8Array(await preview.arrayBuffer()));
}
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(output);
console.log(JSON.stringify({archivo: path.resolve(output), deducible_gs: actual}));
