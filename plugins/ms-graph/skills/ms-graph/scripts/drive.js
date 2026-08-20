// Read personal OneDrive items via Microsoft Graph (requires the Files.Read scope).
//
// Web link:  node drive.js weburl "<path-under-onedrive-root>"
//            prints the item's webUrl — a one-click onedrive.live.com deep link that opens
//            the file or folder in the browser.
// List:      node drive.js list "<folder-path-under-onedrive-root>"
//            prints each child's name and webUrl (path defaults to the drive root).
// Download:  node drive.js download "<path-under-onedrive-root>" "<local-outfile>"
//            writes the item's current cloud bytes to <local-outfile>. Reads the live cloud
//            copy, so it reflects an edit made in Word Online even before the OneDrive
//            desktop client has synced that change back down to the local folder.
//
// Paths are relative to the OneDrive root, e.g. "Claude/job-applications/LasVegasSands".

const fs = require('fs');
const { getGraphClient } = require('./graph-client');

const [command, rawPath, outPath] = process.argv.slice(2);

// Graph addresses a path-based item as /me/drive/root:/<path>: — encode each segment but
// keep the slashes that separate them.
function itemApiPath(p) {
  const clean = String(p || '').replace(/^\/+|\/+$/g, '');
  if (!clean) return '/me/drive/root';
  const encoded = clean.split('/').map(encodeURIComponent).join('/');
  return `/me/drive/root:/${encoded}:`;
}

async function weburl(client) {
  if (!rawPath) throw new Error('weburl requires a path, e.g. weburl "Claude/job-applications"');
  const item = await client.api(itemApiPath(rawPath)).select('name,webUrl').get();
  console.log(item.webUrl);
}

async function list(client) {
  const base = itemApiPath(rawPath);
  const api = base === '/me/drive/root' ? '/me/drive/root/children' : `${base}/children`;
  const data = await client.api(api).select('name,webUrl,folder,file').get();
  const items = data.value || [];
  if (!items.length) { console.log('(empty)'); return; }
  items.forEach(i => {
    const kind = i.folder ? '[dir] ' : '      ';
    console.log(`${kind}${i.name}\n      ${i.webUrl}`);
  });
}

async function download(client) {
  if (!rawPath) throw new Error('download requires a path, e.g. download "Claude/.../file.docx" out.docx');
  if (!outPath) throw new Error('download requires an output file path as the second argument');
  const meta = await client.api(itemApiPath(rawPath)).get();
  const url = meta['@microsoft.graph.downloadUrl'] || meta['@content.downloadUrl'];
  if (!url) throw new Error('no download URL returned for item');
  const res = await fetch(url);
  if (!res.ok) throw new Error(`download failed: HTTP ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  fs.writeFileSync(outPath, buf);
  console.log(`downloaded ${rawPath} -> ${outPath} (${buf.length} bytes)`);
}

if (require.main === module) {
  (async () => {
    const client = await getGraphClient();
    if (command === 'weburl') return weburl(client);
    if (command === 'list') return list(client);
    if (command === 'download') return download(client);
    throw new Error('Specify a command: weburl <path> | list [folder-path] | download <path> <outfile>');
  })().catch(e => { console.error('Error:', e.message); process.exit(1); });
}
