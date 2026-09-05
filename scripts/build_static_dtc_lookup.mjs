import {readFile, writeFile} from "node:fs/promises";

const sourcePath = new URL("../data/fixtures/dtc_catalog.json", import.meta.url);
const outputPath = new URL("../data/fixtures/dtc_catalog.lookup.js", import.meta.url);
const catalog = JSON.parse(await readFile(sourcePath, "utf8"));
const definitions = Object.fromEntries(
  catalog.definitions.map(({code, description_en: description, category}) => [code, [description, category]]),
);
const payload = {
  meta: {
    count: catalog.definitions.length,
    title: catalog.source.title,
    publisher: catalog.source.publisher,
    source_type: catalog.source.source_type,
    source_commit: catalog.source.source_commit,
    license_type: catalog.source.license_type,
    review_status: catalog.source.review_status,
    standard_claim: catalog.source.standard_claim,
  },
  definitions,
};
const notice =
  "/* Derived from data/fixtures/dtc_catalog.json. MIT notice: data/fixtures/dtc_catalog.LICENSE. Community data is unreviewed and not claimed as current SAE/OEM authority. */\n";

await writeFile(outputPath, `${notice}window.ORVECT_DTC_CATALOG=${JSON.stringify(payload)};\n`);
console.log(`Generated ${catalog.definitions.length.toLocaleString("en-US")} static DTC definitions.`);
