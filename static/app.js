const C = {Low:'#7BC8A4', Moderate:'#F2C14E', High:'#F08A3C', Extreme:'#E5484D'};
const $ = id => document.getElementById(id);
let S = null, timer = null, maps = {}, groups = {}, charts = {}, base = null, ready = false;
Chart.defaults.color = '#B9A99B'; Chart.defaults.borderColor = '#3A2E28';
Chart.defaults.font.family = "'IBM Plex Sans',sans-serif";

async function api(url) {
  const r = await fetch(url);
  if (r.status === 401) { location = '/login'; return null; }
  return r.json();
}
function params() { return new URLSearchParams({t: $('t').value, rh: $('rh').value, ws: $('ws').value}); }
function setSliders(p) {
  $('t').value = p.t; $('rh').value = p.rh; $('ws').value = p.ws;
  $('vt').textContent = (+p.t).toFixed(1) + ' °C'; $('vrh').textContent = Math.round(p.rh) + ' %'; $('vws').textContent = (+p.ws).toFixed(1) + ' m/s';
}
async function load(useNasa) {
  S = await api('/api/state' + (useNasa ? '' : '?' + params())); if (!S) return;
  if (useNasa) setSliders(S.params);
  render();
}
const later = () => { clearTimeout(timer); timer = setTimeout(() => load(false), 250); };

function render() {
  const z = S.zones[0];
  $('hn').textContent = Math.round(z.felt) + '°C'; $('hz').textContent = z.zone;
  $('hp').textContent = S.city_level + ' heat stress'; $('hp').style.background = C[S.city_level];
  $('heatbar').innerHTML = S.zones.map(q => `<i style="background:${C[q.level]}"></i>`).join('');
  $('k1').textContent = S.zones.length; $('k2').textContent = S.n_high + ' of ' + S.zones.length;
  $('k3').textContent = S.exposed.toLocaleString(); $('k4').textContent = '+' + S.uhi_avg + ' °C';
  $('src').textContent = S.forecast ? `Model trained on ${S.forecast.days.toLocaleString()} days of NASA POWER data.` : 'NASA POWER unavailable. Using manual values. Connect to the internet once to download it.';
  zoneLayers(); forecastTab(); table(); insights(); planner();
}

function map(id, tiles) {
  const m = L.map(id).setView([26.2483, 68.4097], 12);
  base = tiles; L.tileLayer(tiles.url, tiles.opt).addTo(m); return m;
}
const ESRI = {url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', opt: {maxZoom: 17, attribution: 'Esri'}};
const DARK = {url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', opt: {maxZoom: 19, attribution: '© OpenStreetMap contributors'}};
function nasaUrl() { const d = new Date(Date.now() - 2 * 864e5).toISOString().slice(0, 10);
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/${d}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`; }

function initMaps() {
  maps.sat = map('map1', ESRI); maps.risk = map('map2', DARK);
  groups.sat = L.layerGroup().addTo(maps.sat); groups.risk = L.layerGroup().addTo(maps.risk);
  maps.tile = maps.sat.eachLayer(l => l instanceof L.TileLayer && (maps.satTile = l));
  $('base').onchange = e => { maps.satTile.setUrl(e.target.value === 'nasa' ? nasaUrl() : ESRI.url); maps.satTile.options.maxNativeZoom = e.target.value === 'nasa' ? 9 : 17; };
  $('ov').onchange = zoneLayers;
}
function zoneLayers() {
  ['sat', 'risk'].forEach(k => {
    groups[k].clearLayers();
    if (k === 'sat' && !$('ov').checked) return;
    S.zones.forEach(z => L.circleMarker([z.lat, z.lon], {radius: 8 + z.score / 5, color: '#fff', weight: 1, fillColor: C[z.level], fillOpacity: k === 'sat' ? .65 : .8})
      .bindPopup(`<b>${z.zone}</b><br>Feels like ${z.felt.toFixed(1)} °C<br>Risk: ${z.level}<br>Priority: ${z.score}`).addTo(groups[k]));
  });
}
function table() {
  $('tbl').innerHTML = '<tr><th>Zone</th><th>Risk</th><th>°C</th><th>Priority</th></tr>' + S.zones.map(z =>
    `<tr><td>${z.zone}</td><td><span class="dot" style="background:${C[z.level]}"></span>${z.level}</td><td>${z.felt.toFixed(1)}</td>
    <td style="width:70px"><div class="bar"><i style="width:${z.score}%"></i></div></td></tr>`).join('');
}
function chart(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart($(id), cfg); }
function forecastTab() {
  const f = S.forecast;
  if (!f) { $('fck').innerHTML = '<div class="info">Connect to the internet once. The NASA POWER history is then saved as nasa_power_nawabshah.csv for offline use.</div>'; return; }
  const hot = f.hot;
  const K = (l, v, s, c) => `<div class="kpi"><span>${l}</span><b style="font-size:1.7rem">${v}</b><span style="color:${c || ''}">${s}</span></div>`;
  $('fck').innerHTML = K('Peak max temperature, next 3 days', f.peak + ' °C', 'typical for now: ' + f.typical + ' °C') +
    K('Heatwave signal', hot ? 'Heatwave likely' : 'Within normal range', 'hotter than 95% of past years: ' + f.p95 + ' °C', hot ? C.Extreme : C.Low) +
    K('Model error on unseen year', '±' + f.mae + ' °C', `"same as today" guess: ±${f.base} °C`, C.Low);
  const labels = [...f.hist_dates, ...f.fc_dates], n = f.hist.length;
  const obs = [...f.hist, ...f.fc.map(() => null)];
  const pred = [...f.hist.map((v, i) => i === n - 1 ? v : null), ...f.fc];
  chart('cfc', {type: 'line', data: {labels, datasets: [
    {label: 'NASA observed', data: obs, borderColor: '#F08A3C', backgroundColor: '#F08A3C', tension: .25},
    {label: 'Model forecast', data: pred, borderColor: '#D8CBBE', backgroundColor: '#D8CBBE', borderDash: [6, 4], tension: .25},
    {label: 'Heatwave threshold', data: labels.map(() => f.p95), borderColor: '#E5484D', borderDash: [3, 3], pointRadius: 0}]},
    options: {maintainAspectRatio: false, scales: {y: {title: {display: true, text: 'Max air temperature (°C)'}}}, plugins: {legend: {position: 'bottom'}}}});
  $('fcn').textContent = `Red line: exceeded on only 5% of days around this date since 2015. Data ends ${f.hist_dates.at(-1)} (NASA publishes with a short delay), so the model rolls forward to today.`;
}
function insights() {
  chart('cimp', {type: 'bar', data: {labels: S.importance.map(x => x[0]), datasets: [{data: S.importance.map(x => x[1] * 100), backgroundColor: '#F08A3C', borderRadius: 4}]},
    options: {indexAxis: 'y', maintainAspectRatio: false, plugins: {legend: {display: false}}, scales: {x: {title: {display: true, text: 'Importance (%)'}}}}});
  const cols = [C.Extreme, C.Moderate, C.Low];
  chart('csw', {type: 'line', data: {labels: S.sweep.temps, datasets: Object.entries(S.sweep.series).map(([k, v], i) => ({label: k, data: v, borderColor: cols[i], backgroundColor: cols[i], tension: .3}))},
    options: {maintainAspectRatio: false, plugins: {legend: {position: 'bottom'}}, scales: {x: {title: {display: true, text: 'Air temperature (°C)'}}, y: {title: {display: true, text: 'Feels like (°C)'}}}}});
  $('gap').innerHTML = `Right now the hottest and coolest zones differ by <b>${S.gap} °C</b> in urban heat uplift. A single weather station would miss this difference entirely.`;
}
async function planner() {
  const sel = $('wz'), cur = sel.value;
  if (!sel.options.length) sel.innerHTML = S.zones.map(z => `<option>${z.zone}</option>`).join('');
  if (cur) sel.value = cur;
  $('vtr').textContent = '+' + $('tree').value; $('vrf').textContent = '+' + $('roof').value;
  const q = params(); q.set('zone', sel.value); q.set('tree', $('tree').value); q.set('roof', $('roof').value);
  const w = await api('/api/whatif?' + q); if (!w) return;
  const d = w.after.felt - w.before.felt, K = (l, v, s, c) => `<div class="kpi"><span>${l}</span><b style="font-size:1.8rem">${v}</b><span style="color:${c}">${s}</span></div>`;
  $('wik').innerHTML = K('Feels like today', w.before.felt + ' °C', w.before.level, C[w.before.level]) +
    K('With the plan', w.after.felt + ' °C', (d > 0 ? '+' : '') + d.toFixed(1) + ' °C', d < 0 ? C.Low : '#B9A99B') +
    K('Risk level', w.after.level, 'was ' + w.before.level, C[w.after.level]);
  $('wip').textContent = `Roughly ${w.people.toLocaleString()} residents live in ${sel.value}.`;
}

document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'p-' + b.dataset.t));
  setTimeout(() => { maps.sat.invalidateSize(); maps.risk.invalidateSize(); Object.values(charts).forEach(c => c.resize()); }, 50);
});
['t', 'rh', 'ws'].forEach(i => $(i).oninput = () => { setSliders({t: $('t').value, rh: $('rh').value, ws: $('ws').value}); later(); });
['wz', 'tree', 'roof'].forEach(i => $(i).oninput = () => { clearTimeout(timer); timer = setTimeout(planner, 200); });
document.querySelectorAll('[data-p]').forEach(b => b.onclick = () => { const [t, rh, ws] = b.dataset.p.split(','); setSliders({t, rh, ws}); load(false); });
$('nasa').onclick = () => load(true);
initMaps(); load(true);
