(function(){
  window.scrollTo(0,0);
  document.getElementById('map').setAttribute('tabindex','-1');
  var map=L.map('map',{tapTolerance:25, keyboard:false});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
  map.setView([-27.47,153.03],8);
  var waypoints=[]; var markers=L.layerGroup().addTo(map); var stationLayer=L.layerGroup().addTo(map); var routeLayer=L.layerGroup().addTo(map); var stationsByName={};

  function esc(s){ return String(s||'').replace(/[&<>\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function fmtDur(s){ s=Math.round(Number(s)||0); var h=Math.floor(s/3600), m=Math.round((s%3600)/60); return (h? (h+'h '):'')+m+'m'; }
  function fmtKm(m){ return ((Number(m)||0)/1000).toFixed(1)+' km'; }

  function render(){
    markers.clearLayers();
    var el=document.getElementById('wps'); el.innerHTML='';
    document.getElementById('count').textContent=waypoints.length;
    var pts=[];
    waypoints.forEach(function(w,i){
      pts.push([w.lat,w.lon]);
      var m=L.marker([w.lat,w.lon]).addTo(markers).bindPopup('<b>'+esc(w.name||('Waypoint '+(i+1)))+'</b><br>'+w.lat+', '+w.lon+'<br><a href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(w.lat+','+w.lon)+'&travelmode=driving" target="_blank" rel="noopener">Directions</a>');
      var d=document.createElement('div'); d.className='wp';
      d.innerHTML='<b>'+(i+1)+'. '+esc(w.name||('Waypoint '+(i+1)))+'</b><div class="muted">'+w.lat+', '+w.lon+' · '+esc(w.source||'manual')+'</div><div style="margin-top:.35rem"><button data-i="'+i+'">Remove</button> <a href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(w.lat+','+w.lon)+'&travelmode=driving" target="_blank" rel="noopener" style="color:#7fc8ff">Directions</a></div>';
      d.querySelector('button').addEventListener('click', function(){ waypoints.splice(i,1); render(); });
      el.appendChild(d);
    });
    if(pts.length){ map.fitBounds(L.latLngBounds(pts).pad(0.18)); }
    routeLayer.eachLayer(function(ly){ if(ly.bringToFront) ly.bringToFront(); });
  }

  function addWp(name, lat, lon, source){
    lat=Number(lat); lon=Number(lon);
    if(!isFinite(lat)||!isFinite(lon)) return;
    waypoints.push({name:name||'', lat:lat, lon:lon, source:source||'manual'});
    render();
  }

  function loadStations(){
    fetch('/api/stations/catalog?limit=50000').then(function(r){ return r.json(); }).then(function(d){
      var list=document.getElementById('stationsList'); list.innerHTML='';
      stationLayer.clearLayers();
      (d.stations||[]).forEach(function(s){
        if(!s||!s.name) return;
        stationsByName[s.name]=s;
        var o=document.createElement('option'); o.value=s.name; o.label=s.name+' ('+s.lat+', '+s.lon+')'; list.appendChild(o);
        var lat=Number(s.lat), lon=Number(s.lon);
        if(isFinite(lat)&&isFinite(lon)){
          var sm=L.circleMarker([lat,lon],{radius:5,color:'#7fc8ff',fillColor:'#2f8fd9',fillOpacity:0.75,weight:1.5});
          sm.bindPopup('<b>'+esc(s.name)+'</b><br>'+lat+', '+lon+'<br><button class="add-st" data-name="'+esc(s.name)+'" data-lat="'+lat+'" data-lon="'+lon+'">Add waypoint</button>');
          sm.on('popupopen', function(ev){
            var btn=ev.popup.getElement().querySelector('.add-st');
            if(btn){ btn.addEventListener('click', function(){
              var nm=btn.getAttribute('data-name')||'Station';
              var bl=Number(btn.getAttribute('data-lat')), bo=Number(btn.getAttribute('data-lon'));
              if(!isFinite(bl)||!isFinite(bo)) return;
              addWp(nm, bl, bo, 'station-map');
              map.closePopup();
            }); }
          });
          stationLayer.addLayer(sm);
        }
      });
    });
  }

  function googleNavUrl(points){
    if(!points || points.length<2) return '';
    var origin=points[0].lat+','+points[0].lon;
    var dest=points[points.length-1].lat+','+points[points.length-1].lon;
    var mid=points.slice(1,-1).map(function(p){ return p.lat+','+p.lon; }).join('|');
    var u='https://www.google.com/maps/dir/?api=1&travelmode=driving&origin='+encodeURIComponent(origin)+'&destination='+encodeURIComponent(dest);
    if(mid) u += '&waypoints='+encodeURIComponent(mid);
    return u;
  }

  function buildRoute(){
    if(waypoints.length<2){ document.getElementById('routeInfo').textContent='Need at least 2 waypoints'; return; }
    routeLayer.clearLayers();
    var optimize=!!document.getElementById('optTime').checked;
    var ordered=waypoints.slice();
    var coords=ordered.map(function(w){ return w.lon+','+w.lat; }).join(';');

    function drawFromCoords(arr, dist, dur){
      routeLayer.clearLayers();
      var latlngs=arr.map(function(c){ return [c[1],c[0]]; });
      if(!latlngs.length) return false;
      var line=L.polyline(latlngs,{color:'#ff2d55',weight:6,opacity:0.95}).addTo(routeLayer);
      if(line.bringToFront) line.bringToFront();
      document.getElementById('routeInfo').textContent='Route: '+fmtKm(dist)+' · '+fmtDur(dur)+(optimize?' · optimized':'');
      map.fitBounds(L.latLngBounds(latlngs).pad(0.12));
      return true;
    }

    function drawFallback(orderPoints, note){
      routeLayer.clearLayers();
      var latlngs=orderPoints.map(function(w){ return [Number(w.lat), Number(w.lon)]; }).filter(function(p){ return isFinite(p[0])&&isFinite(p[1]); });
      if(latlngs.length<2){ document.getElementById('routeInfo').textContent='Need at least 2 valid waypoints'; return; }
      var line=L.polyline(latlngs,{color:'#ff2d55',weight:5,opacity:0.85,dashArray:'8,6'}).addTo(routeLayer);
      if(line.bringToFront) line.bringToFront();
      map.fitBounds(L.latLngBounds(latlngs).pad(0.12));
      document.getElementById('routeInfo').textContent='Routing service unavailable; showing straight-line path'+(note?(' ('+note+')'):'');
    }

    var routeWithOrder=function(orderPoints){
      var c2=orderPoints.map(function(w){ return w.lon+','+w.lat; }).join(';');
      return fetch('https://router.project-osrm.org/route/v1/driving/'+c2+'?overview=full&geometries=geojson')
        .then(function(r){ if(!r.ok) throw new Error('http_'+r.status); return r.json(); })
        .then(function(d){
          if(!d || !d.routes || !d.routes.length) throw new Error('route_not_found');
          var rt=d.routes[0];
          var ok=drawFromCoords(rt.geometry.coordinates||[], rt.distance||0, rt.duration||0);
          if(!ok) throw new Error('empty_geometry');
          waypoints=orderPoints; render();
        });
    };

    if(optimize && waypoints.length>2){
      fetch('https://router.project-osrm.org/trip/v1/driving/'+coords+'?source=first&destination=last&roundtrip=false&overview=false')
        .then(function(r){ if(!r.ok) throw new Error('http_'+r.status); return r.json(); })
        .then(function(d){
          if(!d || !d.waypoints || !d.waypoints.length) throw new Error('optimize_failed');
          var ord=d.waypoints.map(function(w,idx){ return {w:w, idx:idx}; })
            .sort(function(a,b){ return (a.w.waypoint_index||0)-(b.w.waypoint_index||0); })
            .map(function(x){ return waypoints[x.idx]; })
            .filter(function(x){ return !!x; });
          return routeWithOrder(ord).catch(function(e){ drawFallback(ord, String(e&&e.message||'route failed')); });
        })
        .catch(function(e){ routeWithOrder(ordered).catch(function(e2){ drawFallback(ordered, String((e2&&e2.message)|| (e&&e.message) || 'failed')); }); });
    } else {
      routeWithOrder(ordered).catch(function(e){ drawFallback(ordered, String(e&&e.message||'failed')); });
    }
  }

  document.getElementById('addStation').addEventListener('click', function(){
    var sp=document.getElementById('stationPick');
    var n=(sp.value||'').trim();
    var s=stationsByName[n]; if(!s) return;
    addWp(n, s.lat, s.lon, 'station');
    sp.value='';
  });
  document.getElementById('addLatLon').addEventListener('click', function(){
    addWp((document.getElementById('wpName').value||'').trim(), document.getElementById('lat').value, document.getElementById('lon').value, 'latlon');
  });
  document.getElementById('addAddr').addEventListener('click', function(){
    var q=(document.getElementById('addr').value||'').trim(); if(!q) return;
    fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+encodeURIComponent(q),{headers:{'Accept':'application/json'}})
      .then(function(r){return r.json();})
      .then(function(a){ if(!a||!a.length) return; addWp(q, a[0].lat, a[0].lon, 'address'); });
  });
  map.on('click', function(ev){ addWp('Map point', ev.latlng.lat, ev.latlng.lng, 'map'); });
  document.getElementById('buildRoute').addEventListener('click', buildRoute);
  document.getElementById('navGoogle').addEventListener('click', function(){
    var u=googleNavUrl(waypoints);
    if(!u){ document.getElementById('routeInfo').textContent='Need at least 2 waypoints for navigation'; return; }
    window.open(u, '_blank');
  });
  document.getElementById('clear').addEventListener('click', function(){ waypoints=[]; routeLayer.clearLayers(); document.getElementById('routeInfo').textContent=''; render(); });

  loadStations(); render();
})();
