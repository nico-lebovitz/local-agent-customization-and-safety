// Adapt this workshop's non-streaming tool API to OpenClaw's SSE transport.
// Tool calls remain structured provider responses; no text is executed here.
import http from 'node:http';
const upstream = 'http://host.openshell.internal:30081';
http.createServer(async (req, res) => {
  try {
    if (!['/v1/models', '/v1/chat/completions'].includes(req.url)) {
      res.writeHead(404).end(); return;
    }
    let raw = ''; for await (const part of req) raw += part;
    const body = raw ? JSON.parse(raw) : null;
    const streaming = body?.stream;
    if (body) { body.stream = false; delete body.stream_options; }
    const response = await fetch(upstream + req.url, {
      method: req.method, headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await response.text();
    if (!response.ok || !streaming) {
      res.writeHead(response.status, {'Content-Type': 'application/json'}).end(text); return;
    }
    const result = JSON.parse(text);
    res.writeHead(200, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'});
    const base = {id: result.id, object: 'chat.completion.chunk', created: result.created, model: result.model};
    for (const choice of result.choices) {
      const delta = {...choice.message};
      if (delta.tool_calls) delta.tool_calls = delta.tool_calls.map((call, index) => ({...call, index}));
      res.write(`data: ${JSON.stringify({...base, choices: [{index: choice.index, delta, finish_reason: null}]})}\n\n`);
      res.write(`data: ${JSON.stringify({...base, choices: [{index: choice.index, delta: {}, finish_reason: choice.finish_reason}]})}\n\n`);
    }
    res.end('data: [DONE]\n\n');
  } catch (error) { res.writeHead(502).end(JSON.stringify({error: {message: error.message}})); }
}).listen(18790, '127.0.0.1');
