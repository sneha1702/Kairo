// Compile one .jsx file (passed as argv[2]) to plain JS on stdout.
// Used by app.py via subprocess so we don't ship Babel to the browser.
const fs = require("fs");
const babel = require("@babel/core");

const path = process.argv[2];
if (!path) {
  console.error("usage: node _compile_jsx.js <file.jsx>");
  process.exit(1);
}

const src = fs.readFileSync(path, "utf8");
const out = babel.transformSync(src, {
  filename: path,
  presets: [["@babel/preset-react", { runtime: "classic" }]],
  babelrc: false,
  configFile: false,
  sourceMaps: false,
});
process.stdout.write(out.code);
