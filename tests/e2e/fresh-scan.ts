import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "../..");

/**
 * A corpus file made byte-unique for this run, as a temp path to upload.
 *
 * The demo database is seeded from the same corpus these specs draw their
 * fixtures from, so a file posted straight off disk is an exact duplicate of a
 * document that is already stored -- which upload refuses (§22). That refusal
 * is the feature working. What it leaves behind is a test suite that passes
 * once and fails on every run after, because the previous run's upload is now
 * the duplicate.
 *
 * Appending a few bytes AFTER a JPEG's end-of-image marker, or after a PDF's
 * %%EOF, changes the file's hash without changing what any reader sees: both
 * formats stop at their terminator. So OCR, the quality gate and extraction
 * all behave exactly as they would on the original.
 */
export function freshScan(relativePath: string): string {
  const source = path.join(REPO_ROOT, relativePath);
  const unique = Buffer.concat([
    fs.readFileSync(source),
    Buffer.from(`\n<!-- mrittika-e2e ${Date.now()} ${Math.random()} -->`),
  ]);
  const out = path.join(
    os.tmpdir(),
    `mrittika-e2e-${Date.now()}-${Math.random().toString(36).slice(2)}` +
      (path.extname(source) || ".jpg"),
  );
  fs.writeFileSync(out, unique);
  return out;
}

