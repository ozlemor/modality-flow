const http = require('http');

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (response) => {
      let body = '';
      response.on('data', (chunk) => {
        body += chunk;
      });
      response.on('end', () => resolve(JSON.parse(body)));
    }).on('error', reject);
  });
}

async function main() {
  const debugPort = process.argv[2] ?? '9223';
  const appPort = process.argv[3] ?? '8090';
  const urlNeedle = process.argv[4] ?? `localhost:${appPort}`;
  const tabs = await getJson(`http://localhost:${debugPort}/json`);
  const page = tabs.find((tab) => tab.type === 'page' && tab.url.includes(urlNeedle));
  if (!page) {
    throw new Error('No Chrome page open on localhost:8090');
  }

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const runtimeErrors = [];

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') {
      runtimeErrors.push(message.params.exceptionDetails.text);
    }
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  };

  await new Promise((resolve) => {
    ws.onopen = resolve;
  });

  function send(method, params = {}) {
    return new Promise((resolve) => {
      const requestId = ++id;
      pending.set(requestId, resolve);
      ws.send(JSON.stringify({ id: requestId, method, params }));
    });
  }

  await send('Runtime.enable');
  await send('Page.enable');
  await send('Runtime.evaluate', {
    expression: 'new Promise((resolve) => setTimeout(resolve, 5000))',
    awaitPromise: true,
  });

  const result = await send('Runtime.evaluate', {
    expression: `({
      title: document.title,
      text: document.body.innerText,
      bodyLength: document.body.innerHTML.length,
      rootChildren: document.getElementById('root')?.children.length ?? 0,
      background: getComputedStyle(document.body).backgroundColor
    })`,
    returnByValue: true,
  });

  ws.close();
  console.log(JSON.stringify({ ...result.result.result.value, runtimeErrors }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
