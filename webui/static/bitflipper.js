(()=>{
  'use strict';
  function eh(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]); }); }
  const parseCSV = t => {
    const l=t.split(/\\r?\\n/).filter(x=>x.trim()); if(!l.length) return [];
    const h=l[0].split(',').map(x=>x.trim());
    return l.slice(1).map(r=>{ const c=r.split(','); const o={}; h.forEach((k,i)=>o[k]=(c[i]||'').trim()); return o; });
  };
  const rowsFromMetaCatalog = cat => {
    const stations=(cat&&cat.stations)||[];
    const sensors=(cat&&cat.sensors)||[];
    const byBom=new Map();
    stations.forEach(s=>{ const k=String(s.bom_stn||s.station_key||'').trim(); if(k) byBom.set(k,s); });
    return sensors.map(sn=>{
      const bom=String(sn.station_bom_stn||'').trim();
      const st=byBom.get(bom)||{};
      return {
        'Site': String(st.name||st.location||'').trim(),
        'Site ID': bom,
        'Sensor': String(sn.sensor_type||'').trim(),
        'Sensor ID': String(sn.sensor_id||sn.sensor_key||'').trim(),
        'site_id': String(sn.arro_site_id||st.arro_site_id||'').trim(),
        'device_id': String(sn.device_id||'').trim(),
      };
    }).filter(r=>r['Sensor ID']);
  };
  const alertFromSensorId = id => { const p=String(id||'').split('.'), l=p[p.length-1]; return /^\d+$/.test(l)?+l:null; };
  const combos=(a,k)=>{ const r=[];(function f(s,c){ if(c.length===k) return r.push(c.slice()); for(let i=s;i<a.length;i++) f(i+1,c.concat(a[i])); })(0,[]); return r; };
  const bin=n=>n.toString(2);
  const formatLocal=d=>{ const p=x=>String(x).padStart(2,'0'); return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };

  const dataSource=document.getElementById('dataSource');
  const csvWrap=document.getElementById('csvWrap');
  const csvFile=document.getElementById('csvFile');
  const stationLookup=document.getElementById('stationLookup');
  const stationSuggestList=document.getElementById('stationSuggestList');
  const useSuggestion=document.getElementById('useSuggestion');
  const alertAddrInput=document.getElementById('alertAddr');
  let hintRows=[];
  let hintMap=new Map();
  let selectedOriginLabel='';
  let selectedOriginSensorId='';

  function buildHints(rows){
    hintRows=(rows||[]).map(r=>Object.assign({},r));
    hintMap=new Map();
    const seen=new Set();
    hintRows.forEach(r=>{
      const site=String(r['Site']||'').trim();
      const siteId=String(r['Site ID']||'').trim();
      const sensor=String(r['Sensor']||'').trim();
      const sid=String(r['Sensor ID']||'').trim();
      const a=alertFromSensorId(sid);
      if(a==null) return;
      const label=(siteId||'n/a')+' · '+(site||'unknown')+' · '+(sensor||'sensor')+' · ALERT '+String(a);
      if(seen.has(label)) return;
      seen.add(label);
      hintMap.set(label, a);
    });
    renderSuggestions();
  }

  function renderSuggestions(){
    const q=String(stationLookup.value||'').trim().toLowerCase();
    const keys=[...hintMap.keys()];
    const list=q?keys.filter(k=>k.toLowerCase().includes(q)):keys;
    const top=list.slice(0,30);
    if(!top.length){ stationSuggestList.style.display='none'; stationSuggestList.innerHTML=''; return; }
    stationSuggestList.innerHTML=top.map(k=>'<div class="sugg-item" data-v="'+eh(k)+'">'+eh(k)+'</div>').join('');
    stationSuggestList.style.display='block';
  }

  function rowsFromUploadFile(){
    return new Promise((resolve,reject)=>{
      const f=csvFile.files[0];
      if(!f) return resolve([]);
      const rd=new FileReader();
      rd.onload=()=>resolve(parseCSV(String(rd.result||'')));
      rd.onerror=()=>reject(new Error('file_read_failed'));
      rd.readAsText(f);
    });
  }

  function loadRowsForSource(){
    if(dataSource.value==='fwlab'){
      return fetch('/api/meta/catalog').then(r=>r.json()).then(cat=>rowsFromMetaCatalog(cat));
    }
    return rowsFromUploadFile();
  }

  function applySuggestion(){
    const q=String(stationLookup.value||'').trim();
    if(!q) return;
    selectedOriginLabel='';
    selectedOriginSensorId='';
    let a = hintMap.get(q);
    let m = null;
    if(a!=null){
      selectedOriginLabel=q;
      m=hintRows.find(r=>{
        const site=String(r['Site']||'').trim();
        const siteId=String(r['Site ID']||'').trim();
        const sensor=String(r['Sensor']||'').trim();
        const sid=String(r['Sensor ID']||'').trim();
        const aa=alertFromSensorId(sid);
        const label=(siteId||'n/a')+' · '+(site||'unknown')+' · '+(sensor||'sensor')+' · ALERT '+String(aa==null?'':aa);
        return label===q;
      }) || null;
    }
    if(a==null){
      const ql=q.toLowerCase();
      m=hintRows.find(r=>{
        const site=String(r['Site']||'').toLowerCase();
        const siteId=String(r['Site ID']||'').toLowerCase();
        const sid=String(r['Sensor ID']||'').toLowerCase();
        const sensor=String(r['Sensor']||'').toLowerCase();
        return site.includes(ql)||siteId.includes(ql)||sid.includes(ql)||sensor.includes(ql);
      }) || null;
      if(m) a=alertFromSensorId(String(m['Sensor ID']||''));
    }
    if(m) selectedOriginSensorId=String(m['Sensor ID']||'').trim();
    if(a!=null) alertAddrInput.value=String(a);
  }

  useSuggestion.addEventListener('click', applySuggestion);
  stationLookup.addEventListener('input', renderSuggestions);
  stationLookup.addEventListener('focus', renderSuggestions);
  stationLookup.addEventListener('change', applySuggestion);
  stationLookup.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ e.preventDefault(); applySuggestion(); stationSuggestList.style.display='none'; } });
  stationSuggestList.addEventListener('click', (e)=>{
    const t=e.target.closest('.sugg-item'); if(!t) return;
    stationLookup.value=t.getAttribute('data-v')||'';
    applySuggestion();
    stationSuggestList.style.display='none';
  });
  document.addEventListener('click', (e)=>{ if(!e.target.closest('.sugg-wrap') && e.target!==useSuggestion) stationSuggestList.style.display='none'; });

  dataSource.onchange=()=>{
    csvWrap.style.display=(dataSource.value==='upload')?'':'none';
    loadRowsForSource().then(buildHints).catch(()=>buildHints([]));
  };
  csvFile.addEventListener('change', ()=>{ if(dataSource.value==='upload') loadRowsForSource().then(buildHints).catch(()=>buildHints([])); });
  dataSource.onchange();

  document.getElementById('runBtn').onclick=()=>{
    const alertAddr=document.getElementById('alertAddr');
    const bitsToFlip=document.getElementById('bitsToFlip');
    const arroBase=document.getElementById('arroBase');
    const out=document.getElementById('output');
    const f=csvFile.files[0];
    const addr=+alertAddr.value, n=+bitsToFlip.value;
    const base=arroBase.value||'https://contrail-bom.onerain.au/graph/';
    if(n<1||addr<0){ out.textContent='Invalid input.'; return; }

    const runWithRows=(rows)=>{
      if(!rows||!rows.length){ out.textContent='No rows found in selected data source.'; return; }
      rows = rows.map(r=>Object.assign({}, r));
      rows.forEach(r=>r._alert=alertFromSensorId(r['Sensor ID']||''));
      const bits=[...Array(bin(addr).length).keys()];
      const map=new Map();
      combos(bits,n).forEach(b=>{ let v=addr; b.forEach(x=>v^=1<<x); if(v!==addr){ if(!map.has(v)) map.set(v,[]); map.get(v).push(b);} });
      const results=[];
      map.forEach((bs,v)=>{ const m=rows.filter(r=>r._alert===v); bs.forEach(b=>{ if(m.length) m.forEach(x=>results.push({b,v,x})); else results.push({b,v,x:null}); }); });
      const originRows = rows.filter(r=>r._alert===addr);
      let originPreferred = null;
      if(selectedOriginSensorId){
        originPreferred = originRows.find(r=>String(r['Sensor ID']||'').trim()===selectedOriginSensorId) || null;
      }
      if(!originPreferred && selectedOriginLabel){
        originPreferred = originRows.find(r=>{
          const site=String(r['Site']||'').trim();
          const siteId=String(r['Site ID']||'').trim();
          const sensor=String(r['Sensor']||'').trim();
          const sid=String(r['Sensor ID']||'').trim();
          const aa=alertFromSensorId(sid);
          const label=(siteId||'n/a')+' · '+(site||'unknown')+' · '+(sensor||'sensor')+' · ALERT '+String(aa==null?'':aa);
          return label===selectedOriginLabel;
        }) || null;
      }
      if(!originPreferred && originRows.length) originPreferred = originRows[0];
      const originKey = originPreferred ? String((originPreferred.site_id||'')+'|'+(originPreferred.device_id||'')) : '';
      const sensors=[...new Set(results.filter(r=>r.x).map(r=>r.x.Sensor))].sort();
      out.innerHTML='';
      const top=document.createElement('div'); top.className='muted'; top.style.marginBottom='.4rem'; top.textContent='Found '+results.length+' candidate rows.'; out.appendChild(top);
      const filt=document.createElement('div');
      filt.innerHTML='<label>Filter by Sensor <select id="sensorFilter"><option value="">All sensors</option>'+sensors.map(s=>'<option>'+eh(s)+'</option>').join('')+'</select></label> <span id="arroFiltered" style="margin-left:.6rem"></span>';
      out.appendChild(filt);
      const wrap=document.createElement('div');
      wrap.innerHTML='<table class="tbl" id="flipTable"><thead><tr><th>Bits</th><th>Dec</th><th>Bin</th><th>Match</th><th>Site</th><th>Site ID</th><th>Sensor</th><th>Sensor ID</th></tr></thead><tbody>'+
        results.map(r=>'<tr data-sensor="'+eh(r.x?.Sensor||'')+'" data-site="'+eh(r.x?.site_id||'')+'" data-device="'+eh(r.x?.device_id||'')+'" data-match="'+(r.x?'1':'0')+'">'+
        '<td class="mono">'+eh(r.b.join(','))+'</td><td>'+eh(r.v)+'</td><td class="mono">'+eh(bin(r.v))+'</td><td class="'+(r.x?'yes':'no')+'">'+(r.x?'YES':'NO')+'</td><td>'+eh(r.x?.Site||'')+'</td><td>'+eh(r.x?.['Site ID']||'')+'</td><td>'+eh(r.x?.Sensor||'')+'</td><td>'+eh(r.x?.['Sensor ID']||'')+'</td></tr>').join('')+
        '</tbody></table>';
      out.appendChild(wrap);

      const updateArro=()=>{
        const now=new Date(), start=new Date(now-7*86400e3);
        const p=new URLSearchParams({refresh:'off',markers:'false',legend:'true',bin:'86400',time_zone:'Australia/Brisbane',invalid:'true',has_regular_sensors:'true',has_forecast_sensors:'false',for_forecast:'false',hidden_devices:'none',data_start:formatLocal(start),data_end:formatLocal(now)});
        const seen=new Set();
        // Always keep one baseline trace: the original selected sensor/source for this ALERT address.
        if(originKey && originKey!=='|'){ seen.add(originKey); p.append('devices[]',originKey); }
        // Add currently visible matched bit-flip candidates.
        document.querySelectorAll('#flipTable tbody tr').forEach(tr=>{ if(tr.style.display==='none'||tr.dataset.match!=='1') return; const k=tr.dataset.site+'|'+tr.dataset.device; if(!seen.has(k)){ seen.add(k); p.append('devices[]',k);} });
        const c=document.getElementById('arroFiltered'); c.innerHTML='';
        if(seen.size){ const a=document.createElement('a'); a.href=base+'?'+p.toString(); a.target='_blank'; a.rel='noopener'; a.textContent='Open ARRO graph ('+seen.size+' traces incl. original ALERT '+addr+')'; c.appendChild(a); }
      };
      document.getElementById('sensorFilter').onchange=(e)=>{ const v=e.target.value; document.querySelectorAll('#flipTable tbody tr').forEach(tr=>tr.style.display=(!v||tr.dataset.sensor===v)?'':'none'); updateArro(); };
      updateArro();
    };

    if(dataSource.value==='upload' && !f){ out.textContent='Choose a CSV file first, or switch data source to FW-LAB catalog.'; return; }
    out.textContent = (dataSource.value==='fwlab') ? 'Loading FW-LAB catalog…' : 'Loading CSV…';
    loadRowsForSource().then(runWithRows).catch(()=>{ out.textContent='Failed to load selected data source.'; });
  };
})();
