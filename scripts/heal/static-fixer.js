const fs = require('fs');
const path = require('path');

const SKIP_DIRS = new Set([
  '.git',
  '.github',
  'node_modules',
  'dist',
  'build',
  'coverage',
  '.heal_metrics',
  'scripts',
  'src',
  'lib',
  'server',
  'test',
  'tests',
  '__tests__',
]);
const STATIC_EXTENSIONS = new Set(['.html', '.htm', '.css', '.js']);

function walkStaticFiles(dir = process.cwd(), files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        walkStaticFiles(path.join(dir, entry.name), files);
      }
      continue;
    }

    const ext = path.extname(entry.name).toLowerCase();
    if (STATIC_EXTENSIONS.has(ext)) {
      files.push(path.join(dir, entry.name));
    }
  }

  return files;
}

function toRelative(file) {
  return path.relative(process.cwd(), file) || file;
}

function fileExistsFromHtml(htmlFile, reference) {
  if (!reference || reference.startsWith('#')) return true;
  if (/^(https?:)?\/\//i.test(reference)) return true;
  if (/^(mailto|tel|javascript):/i.test(reference)) return true;

  const cleanRef = reference.split('#')[0].split('?')[0];
  if (!cleanRef) return true;

  return fs.existsSync(path.resolve(path.dirname(htmlFile), cleanRef));
}

function fixHtml(file) {
  let content = fs.readFileSync(file, 'utf-8');
  const before = content;

  content = content.replace(/<html(?![^>]*\blang=)([^>]*)>/i, '<html lang="en"$1>');

  if (!/<meta\s+name=["']viewport["']/i.test(content)) {
    content = content.replace(
      /<head([^>]*)>/i,
      '<head$1>\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">'
    );
  }

  if (!/<title>[\s\S]*?<\/title>/i.test(content)) {
    const title = path.basename(file, path.extname(file)).replace(/[-_]+/g, ' ') || 'Website';
    content = content.replace(/<head([^>]*)>/i, `<head$1>\n    <title>${title}</title>`);
  }

  content = content.replace(/<img\b([^>]*?)>/gi, (match, attrs) => {
    if (/\balt\s*=/.test(attrs)) return match;

    const srcMatch = attrs.match(/\bsrc\s*=\s*["']([^"']+)["']/i);
    const src = srcMatch ? srcMatch[1] : '';
    const fallback = src ? path.basename(src, path.extname(src)).replace(/[-_]+/g, ' ') : '';
    return `<img${attrs} alt="${fallback}">`;
  });

  content = content.replace(/<a\b([^>]*?)href=["']([^"']+)["']([^>]*)>([\s\S]*?)<\/a>/gi, (match, beforeHref, href, afterHref, text) => {
    if (fileExistsFromHtml(file, href)) return match;
    return `<a${beforeHref}href="#"${afterHref}>${text}</a>`;
  });

  if (content !== before) {
    fs.writeFileSync(file, content);
    return true;
  }

  return false;
}

function fixCss(file) {
  let content = fs.readFileSync(file, 'utf-8');
  const before = content;

  content = content.replace(/\bcolr\s*:/gi, 'color:');
  content = content.replace(/([^\s;{}][^;{}\n]*:\s*[^;{}\n]+)(?=\n\s*[A-Za-z-]+\s*:)/g, '$1;');
  content = content.replace(/([^\s;{}][^;{}\n]*:\s*[^;{}\n]+)(?=\n\s*})/g, '$1;');

  if (content !== before) {
    fs.writeFileSync(file, content);
    return true;
  }

  return false;
}

function fixJs(file) {
  let content = fs.readFileSync(file, 'utf-8');
  const before = content;

  content = content
    .split('\n')
    .filter((line) => !/^\s*console\.log\([^)]*\);?\s*$/.test(line))
    .join('\n');

  content = content.replace(/([^\s;{}][^;{}\n]*\))(?=\n\s*[})])/g, '$1;');

  if (content !== before) {
    fs.writeFileSync(file, content);
    return true;
  }

  return false;
}

function runStaticAutofix() {
  const modifiedFiles = [];

  for (const file of walkStaticFiles()) {
    const ext = path.extname(file).toLowerCase();
    let changed = false;

    if (ext === '.html' || ext === '.htm') changed = fixHtml(file);
    if (ext === '.css') changed = fixCss(file);
    if (ext === '.js') changed = fixJs(file);

    if (changed) {
      modifiedFiles.push(file);
    }
  }

  if (modifiedFiles.length > 0) {
    console.log(`Static autofix modified ${modifiedFiles.length} file(s):`);
    modifiedFiles.forEach((file) => console.log(`- ${toRelative(file)}`));
  } else {
    console.log('Static autofix found no safe changes to apply.');
  }

  return modifiedFiles;
}

module.exports = { runStaticAutofix, walkStaticFiles };
