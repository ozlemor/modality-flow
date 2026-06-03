const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const PORT = Number(process.env.PUBLIC_PROXY_PORT ?? 8093);
const WEB_TARGET = process.env.PUBLIC_WEB_TARGET ?? 'http://localhost:8091';
const API_TARGET = process.env.PUBLIC_API_TARGET ?? 'http://localhost:3001';

function proxyRequest(clientReq, clientRes, targetBase) {
  const target = new URL(clientReq.url, targetBase);
  const proxy = http.request(
    target,
    {
      method: clientReq.method,
      headers: {
        ...clientReq.headers,
        host: target.host,
      },
    },
    (proxyRes) => {
      clientRes.writeHead(proxyRes.statusCode ?? 502, {
        ...proxyRes.headers,
        'access-control-allow-origin': '*',
      });
      proxyRes.pipe(clientRes);
    },
  );

  proxy.on('error', (error) => {
    clientRes.writeHead(502, { 'content-type': 'application/json' });
    clientRes.end(JSON.stringify({ error: 'Proxy target unavailable', detail: error.message }));
  });

  clientReq.pipe(proxy);
}

const server = http.createServer((req, res) => {
  if (req.url === '/app-context.json') {
    const contextPath = path.join(__dirname, '..', 'docs', 'app-context.json');
    fs.readFile(contextPath, 'utf8', (error, content) => {
      if (error) {
        res.writeHead(404, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: 'app-context.json not found' }));
        return;
      }
      res.writeHead(200, {
        'content-type': 'application/json; charset=utf-8',
        'access-control-allow-origin': '*',
      });
      res.end(content);
    });
    return;
  }

  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
      'access-control-allow-headers': 'content-type,authorization',
    });
    res.end();
    return;
  }

  const target = req.url.startsWith('/api/v1') || req.url.startsWith('/realtime') ? API_TARGET : WEB_TARGET;
  proxyRequest(req, res, target);
});

server.listen(PORT, () => {
  console.log(`Public proxy listening on http://localhost:${PORT}`);
  console.log(`Web target: ${WEB_TARGET}`);
  console.log(`API target: ${API_TARGET}`);
});
