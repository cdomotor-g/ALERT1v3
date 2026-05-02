(function(){
  function g(o,k,d){ return (o && o[k]!==undefined && o[k]!==null)?o[k]:d; }
  function ageClass(ts){
    if(!ts) return 'bad';
    var t=Date.parse(ts); if(!isFinite(t)) return 'bad';
    var m=(Date.now()-t)/60000;
    if(m<5) return 'good';
    if(m<30) return 'warn';
    return 'bad';
  }
  function fmtAge(ts){
    if(!ts) return 'n/a';
    var t=Date.parse(ts); if(!isFinite(t)) return String(ts);
    var s=Math.max(0,Math.floor((Date.now()-t)/1000));
    if(s<60) return s+'s';
    var m=Math.floor(s/60); if(m<60) return m+'m';
    var h=Math.floor(m/60); return h+'h '+(m%60)+'m';
  }
  function load(){
    Promise.all([
      fetch('/api/control/policy').then(r=>r.json()).catch(()=>({})),
      fetch('/api/deployment_role').then(r=>r.json()).catch(()=>({})),
      fetch('/api/control/receivers').then(r=>r.json()).catch(()=>({receivers:[]})),
      fetch('/api/control/state_summary').then(r=>r.json()).catch(()=>({}))
    ]).then(function(v){
      var policy=v[0]||{}, role=v[1]||{}, rr=v[2]||{}, ss=v[3]||{};
      var acp=g(ss,'s3_active_control_plane',{})||{};
      var aep=g(ss,'s3_active_endpoint',{})||{};
      var cp=document.getElementById('cp');
      cp.innerHTML=''
        +'<div>Role: <strong>'+String(g(role,'role','unknown'))+'</strong></div>'
        +'<div>Ingest auth enabled: <strong>'+(g(policy,'enabled',false)?'yes':'no')+'</strong></div>'
        +'<div>Ingest localhost bypass: <strong>'+(g(policy,'allowLocalhostWithoutToken',true)?'yes':'no')+'</strong></div>'
        +'<div>Max events/ingest: <strong>'+String(g(policy,'maxEventsPerIngest','n/a'))+'</strong></div>'
        +'<div style="margin-top:.45rem">Active CP host (S3): <strong>'+String(g(acp,'active_host','n/a'))+'</strong> · Snapshot <span class="muted">'+String(g(acp,'snapshot','n/a'))+'</span></div>'
        +'<div>Active endpoint (S3): <strong>'+String(g(aep,'activeBaseUrl','n/a'))+'</strong></div>'
        +'<div>Active endpoint (local pointer): <strong>'+String(g(ss,'local_active_base_url','n/a'))+'</strong></div>';

      var rows=g(rr,'receivers',[])||[];
      if(!rows.length){ document.getElementById('rx').textContent='no receiver ingest yet'; }
      var tr=rows.map(function(r){
        var ts=g(r,'last_ts','');
        var cls=ageClass(ts);
        return '<tr>'
          +'<td>'+String(g(r,'rxs_id',''))+'</td>'
          +'<td class="'+cls+'">'+fmtAge(ts)+'</td>'
          +'<td>'+String(ts||'')+'</td>'
          +'<td>'+String(g(r,'event_count',0))+'</td>'
          +'<td>'+String(g(g(r,'heartbeat',{}),'state',''))+'</td>'
          +'</tr>';
      }).join('');
      if(rows.length){ document.getElementById('rx').innerHTML='<table class="tbl"><thead><tr><th>Receiver</th><th>Age</th><th>Last seen (UTC)</th><th>Events</th><th>Heartbeat</th></tr></thead><tbody>'+tr+'</tbody></table>'; }
      fetch('/api/receivers_registry').then(function(r){return r.json();}).then(function(reg){
        var rr=(reg&&reg.receivers)||[];
        document.getElementById('regMsg').textContent='registry entries: '+rr.length;
        if(!rr.length){ document.getElementById('regTable').textContent='no receivers'; return; }
        var t=rr.map(function(x){
          return '<tr data-rxid="'+String(x.rxs_id||'')+'">'
            +'<td>'+String(x.rxs_id||'')+'</td>'
            +'<td><input data-k="name" value="'+String(x.name||'').replace(/"/g,'&quot;')+'"></td>'
            +'<td><input data-k="location" value="'+String(x.location||'').replace(/"/g,'&quot;')+'"></td>'
            +'<td><input data-k="base_url" value="'+String(x.base_url||'').replace(/"/g,'&quot;')+'"></td>'
            +'<td><button class="regSave">Save</button> <button class="regDel">Delete</button></td>'
            +'</tr>';
        }).join('');
        document.getElementById('regTable').innerHTML='<table class=\"tbl\"><thead><tr><th>rxs_id</th><th>Name</th><th>Location</th><th>Base URL</th><th>Action</th></tr></thead><tbody>'+t+'</tbody></table>' + '<div style=\"margin-top:.5rem\">' + '<input id=\"regNewId\" placeholder=\"rxs_id (0002)\" style=\"width:9rem\"> ' + '<input id=\"regNewName\" placeholder=\"Name\" style=\"width:10rem\"> ' + '<input id=\"regNewLoc\" placeholder=\"Location\" style=\"width:10rem\"> ' + '<input id=\"regNewBase\" placeholder=\"Base URL\" style=\"width:16rem\"> ' + '<button id=\"regAdd\">Add</button>' + '</div>';
        document.querySelectorAll('#regTable .regSave').forEach(function(b){ b.addEventListener('click', function(){
          var tr=b.closest('tr'); if(!tr) return;
          var rid=tr.getAttribute('data-rxid')||'';
          var body={op:'upsert',item:{rxs_id:rid,name:(tr.querySelector('input[data-k="name"]')||{}).value||'',location:(tr.querySelector('input[data-k="location"]')||{}).value||'',base_url:(tr.querySelector('input[data-k="base_url"]')||{}).value||''}};
          fetch('/api/receivers_registry_update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
            .then(function(r){return r.json();})
            .then(function(d){ document.getElementById('regMsg').textContent = d.ok ? ('saved '+rid) : ('save failed: '+(d.error||'unknown')); })
            .catch(function(){ document.getElementById('regMsg').textContent='save failed'; });
        }); });

        document.querySelectorAll('#regTable .regDel').forEach(function(b){ b.addEventListener('click', function(){
          var tr=b.closest('tr'); if(!tr) return;
          var rid=tr.getAttribute('data-rxid')||'';
          if(!rid) return;
          fetch('/api/receivers_registry_update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'delete',rxs_id:rid})})
            .then(function(r){return r.json();})
            .then(function(d){ document.getElementById('regMsg').textContent = d.ok ? ('deleted '+rid) : ('delete failed: '+(d.error||'unknown')); load(); })
            .catch(function(){ document.getElementById('regMsg').textContent='delete failed'; });
        }); });
        var addBtn=document.getElementById('regAdd');
        if(addBtn){ addBtn.addEventListener('click', function(){
          var rid=((document.getElementById('regNewId')||{}).value||'').trim().toUpperCase();
          var body={op:'upsert',item:{
            rxs_id:rid,
            name:((document.getElementById('regNewName')||{}).value||'').trim(),
            location:((document.getElementById('regNewLoc')||{}).value||'').trim(),
            base_url:((document.getElementById('regNewBase')||{}).value||'').trim()||'local'
          }};
          fetch('/api/receivers_registry_update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
            .then(function(r){return r.json();})
            .then(function(d){ document.getElementById('regMsg').textContent = d.ok ? ('added '+rid) : ('add failed: '+(d.error||'unknown')); load(); })
            .catch(function(){ document.getElementById('regMsg').textContent='add failed'; });
        }); }
      }).catch(function(){ document.getElementById('regMsg').textContent='registry load failed'; });
      document.getElementById('msg').textContent='updated '+new Date().toLocaleTimeString();
    }).catch(function(){ document.getElementById('msg').textContent='refresh failed'; });
  }
  document.getElementById('refresh').addEventListener('click', load);
  load(); setInterval(load, 15000);
})();
