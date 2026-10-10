
  const liveStatus = document.getElementById('live-status');
  liveStatus.hidden = false;
  let liveEtag = null;
  function setLiveStatus(mode, message, detail = '') {
    liveStatus.className = `live-status ${mode}`;
    liveStatus.textContent = message;
    liveStatus.title = detail;
  }
  async function refreshLiveGraph() {
    setLiveStatus('syncing', 'Live · syncing…');
    const headers = liveEtag ? {'If-None-Match': liveEtag} : {};
    try {
      const response = await fetch('/api/graph', {cache: 'no-store', headers});
      if (response.status === 304) {
        setLiveStatus('connected', `Live · graph ${data.graph_version} · up to date`);
        return;
      }
      if (!response.ok) throw new Error(`Graph request failed (${response.status})`);
      const nextData = await response.json();
      liveEtag = response.headers.get('ETag');
      applyData(nextData);
      setLiveStatus('connected', `Live · graph ${data.graph_version} · updated just now`);
    } catch (error) {
      setLiveStatus('error', 'Live · refresh failed; showing last valid graph', error.message);
    }
  }
  const events = new EventSource('/events');
  events.addEventListener('ready', event => {
    const publication = JSON.parse(event.data);
    if (publication.graph_version !== data.graph_version) {
      refreshLiveGraph();
      return;
    }
    liveEtag = `"${publication.etag}"`;
    setLiveStatus('connected', `Live · graph ${data.graph_version} · connected`);
  });
  events.addEventListener('graph', () => refreshLiveGraph());
  events.addEventListener('graph-error', event => {
    const publication = JSON.parse(event.data);
    setLiveStatus('error', 'Live · publication rejected; showing last valid graph', publication.message);
  });
  events.onerror = () => setLiveStatus('error', 'Live · reconnecting…', 'The event stream was interrupted.');
