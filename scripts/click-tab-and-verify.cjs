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
  const debugPort = process.argv[2];
  const appPort = process.argv[3];
  const label = process.argv[4];
  const tabs = await getJson(`http://127.0.0.1:${debugPort}/json`);
  const page = tabs.find((tab) => tab.type === 'page' && tab.url.includes(`localhost:${appPort}`));
  if (!page) throw new Error('Page not found');

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const runtimeErrors = [];
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') runtimeErrors.push(message.params.exceptionDetails.text);
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
  await send('Runtime.evaluate', {
    expression: `
      [...document.querySelectorAll('*')]
        .find((node) => node.innerText && node.innerText.trim() === ${JSON.stringify(label)})
        ?.click()
    `,
  });
  await send('Runtime.evaluate', {
    expression: 'new Promise((resolve) => setTimeout(resolve, 2500))',
    awaitPromise: true,
  });
  const result = await send('Runtime.evaluate', {
    expression: `({
      title: document.title,
      text: document.body.innerText,
      rootChildren: document.getElementById('root')?.children.length ?? 0,
      bodyLength: document.body.innerHTML.length
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
