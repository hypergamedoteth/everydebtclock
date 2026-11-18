/* Checks the browser math in your-share/share.js against data.json. */
const fs = require("fs");
const expectShare = process.argv[2];
const expectCA = process.argv[3];
const expectHH = process.argv[4];
const expectSentence = process.argv[5];
eval(fs.readFileSync("your-share/share.js", "utf8"));
const S = globalThis.EDCShare;
const D = JSON.parse(fs.readFileSync("your-share/data.json", "utf8"));

function assert(cond, msg) {
  if (!cond) {
    console.error(msg || "assertion failed");
    process.exit(1);
  }
}

const plain = S.compute(D, {});
assert(plain.share === D.debt / D.population, "share is not debt / population");
assert(plain.yearDebt == null && !plain.yearMissing, "blank year should not invent a birth-year debt");
assert(S.money(plain.share, 2) === expectShare, "share text " + S.money(plain.share, 2) + " != " + expectShare);

const y = S.compute(D, {born: "1985", state: "california", hh: "3", income: "$80,000"});
assert(y.yearDebt === D.years["1985"][0], "1985 debt was not the historical total");
assert(y.yearPop === D.years["1985"][2], "1985 population");
assert(y.yearPer === y.yearDebt / y.yearPop, "1985 per person");
assert(y.multiple === D.debt / y.yearDebt, "growth multiple");
assert(y.state && y.state.slug === "california", "state lookup");
assert(S.money(y.state.debt / y.state.pop, 2) === expectCA, "california per person " + S.money(y.state.debt / y.state.pop, 2));
assert(y.household === y.share * 3, "household is not per-person times size");
assert(Math.abs(y.incomeYears - y.household / 80000) < 1e-9, "income years");
assert(S.money(D.debt / D.households.count, 2) === expectHH, "census per household");
assert(S.sentence(y) === expectSentence, S.sentence(y) + " != " + expectSentence);

const y2026 = S.compute(D, {born: "2026"});
assert(y2026.yearDebt > 0 && y2026.yearPer == null && y2026.yearPopMissing, "2026 population must stay missing");
assert(S.popMissingText(D, y2026).indexOf("don't estimate") >= 0, "2026 must say it is not estimated");

const missing = S.compute(D, {born: "1700"});
assert(missing.yearMissing && missing.yearDebt == null && missing.multiple == null, "1700 must not be guessed");
assert(S.sentence(missing).indexOf("don't estimate") >= 0, S.sentence(missing));

assert(S.growthClause(0.5) === "it is now 0.50× that level.", S.growthClause(0.5));
assert(S.growthClause(1.001) === "it is about the same size.", S.growthClause(1.001));
assert(S.growthClause(22.274) === "it has grown 22.3× since.", S.growthClause(22.274));
assert(S.compute(D, {hh: "0"}).household == null, "household 0");
assert(S.compute(D, {hh: "21"}).hhError, "household 21");
assert(S.compute(D, {state: "atlantis"}).stateError, "unknown state");
assert(S.compute(D, {income: "-5"}).income == null, "negative income");

const url = S.sharePath(D, {born: "1985", state: "California", hh: "3", income: "80000"});
assert(url === "/your-share/born/1985/?state=california&hh=3&income=80000", url);
const early = S.sharePath(D, {born: "1890"});
assert(early === "/your-share/?born=1890", early);

console.log("share checks ok", expectShare);
