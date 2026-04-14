/**
 * Generates PNG icons from icon.svg using Node.js + sharp (or canvas).
 * Run once: node generate_icons.js
 *
 * Install: npm install sharp
 */

const fs = require("fs");
const path = require("path");

async function generate() {
  let sharp;
  try {
    sharp = require("sharp");
  } catch {
    console.error("Install sharp first: npm install sharp");
    process.exit(1);
  }

  const svgPath = path.join(__dirname, "icons", "icon.svg");
  const svg = fs.readFileSync(svgPath);
  const sizes = [16, 48, 128];

  for (const size of sizes) {
    const out = path.join(__dirname, "icons", `icon${size}.png`);
    await sharp(svg).resize(size, size).png().toFile(out);
    console.log(`Generated ${out}`);
  }
}

generate().catch(console.error);
