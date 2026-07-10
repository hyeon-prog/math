#!/usr/bin/env node
/**
 * =====================================================================
 * 온통청년 청년정책 → data/policies.json 생성 스크립트
 * ---------------------------------------------------------------------
 * 데이터 소스 (우선순위):
 *  1) 공식 오픈API getPlcy (YOUTH_API_KEY 필요)
 *     — 인증키 승인 전에는 모든 필드가 null로 마스킹되어 옴
 *  2) 온통청년 웹 통합검색 JSON (portalPolicySearch, 키 불필요)
 *     — 사이트 프론트엔드가 쓰는 공개 엔드포인트, 전체 필드 제공
 *  3) 둘 다 실패 시 큐레이션 데이터(data/curated.json)만으로 생성
 *
 * 실행:  node scripts/fetch-policies.mjs            (포털 폴백 사용)
 *        YOUTH_API_KEY=<키> node scripts/...        (공식 API 우선)
 *        YOUTH_API_MOCK=<파일> node scripts/...     (목 응답 테스트)
 *
 * GitHub Actions(.github/workflows/update-data.yml)가 매일 실행합니다.
 * ===================================================================== */

import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const API_URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy";
const PORTAL_URL = "https://www.youthcenter.go.kr/pubot/search/portalPolicySearch";
const MAX_API_ITEMS = 30; // 페이지 성능을 위해 API 항목 수 제한

/* ---------------- 코드 → 값 매핑 테이블 ---------------- */

// 법정동코드 앞 2자리 → 시/도명 (정적 폴백 — 실행 시 getCtpvCd API로 최신화)
// 2026년 행정구역 개편 반영: 12 = 전남광주통합특별시 등
const SIDO_BY_PREFIX = {
  "11": "서울특별시", "12": "전남광주통합특별시", "26": "부산광역시",
  "27": "대구광역시", "28": "인천광역시", "29": "광주광역시",
  "30": "대전광역시", "31": "울산광역시", "36": "세종특별자치시",
  "41": "경기도", "43": "충청북도", "44": "충청남도", "46": "전라남도",
  "47": "경상북도", "48": "경상남도", "50": "제주특별자치도",
  "51": "강원특별자치도", "52": "전북특별자치도",
};
let SIDO_NAMES = [...new Set(Object.values(SIDO_BY_PREFIX))];

/** 온통청년 시/도 코드 API(키 불필요)로 최신 행정구역 반영 */
async function refreshSidoMap() {
  try {
    const res = await fetch(
      "https://www.youthcenter.go.kr/go/ythip/getCtpvCd?rtnType=json",
      { signal: AbortSignal.timeout(15000) }
    );
    const json = await res.json();
    const list = json?.admVOList?.admVOList;
    if (Array.isArray(list)) {
      list.forEach(({ admCode, admCodeNm }) => {
        if (admCode && admCodeNm) SIDO_BY_PREFIX[String(admCode).slice(0, 2)] = admCodeNm;
      });
      SIDO_NAMES = [...new Set(Object.values(SIDO_BY_PREFIX))];
      console.log(`시/도 코드 ${list.length}건 동기화`);
    }
  } catch { /* 실패 시 정적 폴백 사용 */ }
}

// 정책 분류 텍스트 → 사이트 카테고리 (키워드 우선순위 순)
const CATEGORY_RULES = [
  [/주거|전월세|월세|임대|이사/, "주거"],
  [/창업/, "창업"],
  [/일자리|취업|일경험|채용/, "취업"],
  [/금융|자산|대출|통장/, "금융"],
  [/교육|역량|자격증|장학/, "교육"],
  [/복지|문화|건강|생활/, "생활지원"],
  [/참여|권리/, "참여·권리"],
];

function normalizeCategory(...texts) {
  const t = texts.map(clean).join(" ");
  for (const [re, cat] of CATEGORY_RULES) if (re.test(t)) return cat;
  return clean(texts[1]).split(",")[0] || "기타";
}

// 취업요건코드(공식 API) → 사이트 취업상태 값
const JOB_CODE_MAP = {
  "0013001": "employed",      // 재직자
  "0013002": "self-employed", // 자영업자
  "0013003": "jobseeker",     // 미취업자
  "0013004": "freelancer",    // 프리랜서
};

// 취업상태명(포털 검색) 키워드 → 사이트 취업상태 값
const EMPM_NAME_MAP = [
  [/재직/, "employed"],
  [/자영업/, "self-employed"],
  [/미취업|구직/, "jobseeker"],
  [/프리랜서/, "freelancer"],
];

/* ---------------- 유틸 ---------------- */

const clean = (v) =>
  String(v ?? "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

const num = (v) => {
  const n = parseInt(String(v ?? "").replace(/\D/g, ""), 10);
  return Number.isFinite(n) ? n : null;
};

/** KST 기준 오늘 날짜 YYYYMMDD */
function todayYmdKst() {
  const kst = new Date(Date.now() + 9 * 3600 * 1000);
  return kst.toISOString().slice(0, 10).replace(/-/g, "");
}

/** 이름 정규화 — 중복 판단용 (공백·괄호·특수문자 제거) */
const normName = (s) => clean(s).replace(/[\s()\[\]「」·+ⅠⅡ\-~]/g, "");

/* ---------------- 필드 매핑 ---------------- */

/**
 * 지역 판정: 법정동코드(zipCd) 우선, 없으면 지역명 문자열(stdgNm)에서
 * 시/도명을 스캔. 10개 시/도 이상이거나 판별 불가면 "전국".
 */
function parseRegions(zipCd, stdgNm) {
  const prefixes = new Set(
    String(zipCd ?? "").split(",").map((s) => s.trim().slice(0, 2)).filter(Boolean)
  );
  let sidos = [...new Set([...prefixes].map((p) => SIDO_BY_PREFIX[p]).filter(Boolean))];

  if (sidos.length === 0 && stdgNm) {
    // 전체 시/도명만 정확히 매칭 (축약 매칭은 "경기도 광주시" 같은 오분류를 유발)
    const names = clean(stdgNm);
    sidos = SIDO_NAMES.filter((n) => names.includes(n));
  }
  if (sidos.length === 0 || sidos.length >= 10) return ["전국"];
  return sidos;
}

/**
 * 신청기간 판정 → { open, deadline }
 * aplyYmd("20260101 ~ 20261231") > 신청기간구분코드 > 사업기간 순으로 판단.
 * 코드: 0057001 특정기간 / 0057002 상시 / 0057003 마감
 */
function parseApply(raw, today) {
  const ymd = clean(raw.aplyYmd);
  const m = ymd.match(/(\d{8})\s*~\s*(\d{8})/);
  if (m) {
    const open = today >= m[1] && today <= m[2];
    const fmt = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    return { open, deadline: `${fmt(m[1])} ~ ${fmt(m[2])}${open ? "" : " (접수 기간 아님)"}` };
  }

  const se = clean(raw.aplyPrdSeCd);
  if (se === "0057003") return { open: false, deadline: "접수 마감 (공고 확인)" };

  const end = clean(raw.bizPrdEndYmd).replace(/\D/g, "");
  if (end.length === 8 && end < today) {
    return { open: false, deadline: `사업기간 종료 (~${end.slice(0, 4)}-${end.slice(4, 6)}-${end.slice(6, 8)})` };
  }
  if (se === "0057001") return { open: true, deadline: "기간제 모집 — 상세 공고에서 접수기간 확인" };
  return { open: true, deadline: "상시 신청 (상세 공고 확인)" };
}

/** 주관기관명으로 정부정책/지자체 구분 (중앙부처는 보통 부·처·청·위원회로 끝남) */
function classifyType(raw) {
  const org = clean(raw.sprvsnInstCdNm || raw.rgtrUpInstCdNm || raw.operInstCdNm);
  if (/(특별시|광역시|자치시|자치도|도청|시청|군청|구청)/.test(org)) return "local";
  if (/(도|시|군|구)$/.test(org) && !/(공사|공단|진흥원|재단|연구원)$/.test(org)) return "local";
  return "policy";
}

/** 취업상태: 코드(공식 API) 또는 상태명(포털) → 사이트 값 배열 */
function parseEmployment(raw) {
  const fromCode = String(raw.jobCd ?? "").split(",")
    .map((c) => JOB_CODE_MAP[c.trim()]).filter(Boolean);
  if (fromCode.length) return [...new Set(fromCode)];

  const name = clean(raw.empmSttsNm);
  if (!name || /제한없음|무관/.test(name)) return null;
  const fromName = EMPM_NAME_MAP.filter(([re]) => re.test(name)).map(([, v]) => v);
  return fromName.length ? [...new Set(fromName)] : null;
}

/** 혼인상태명 → "married" | "single" | null */
function parseMarital(raw) {
  const name = clean(raw.mrgSttsNm);
  if (/기혼/.test(name) && !/미혼/.test(name)) return "married";
  if (/미혼/.test(name) && !/기혼/.test(name)) return "single";
  return null;
}

/** API/포털 원본 1건 → 사이트 아이템 스키마 (camelCase 정규화 이후) */
function mapPolicy(raw, today) {
  const { open, deadline } = parseApply(raw, today);
  const minAge = num(raw.sprtTrgtMinAge);
  const maxAge = num(raw.sprtTrgtMaxAge);

  const ageText =
    minAge || maxAge ? `만 ${minAge ?? "제한없음"}~${maxAge ?? "제한없음"}세` : "";
  const targetSrc = clean(raw.addAplyQlfcCndCn) || clean(raw.plcyExplnCn);

  return {
    id: `yc-${clean(raw.plcyNo) || normName(raw.plcyNm).slice(0, 20)}`,
    type: classifyType(raw),
    open,
    source: "youthcenter",
    name: trunc(clean(raw.plcyNm), 60),
    category: normalizeCategory(raw.lclsfNm, raw.mclsfNm, raw.plcyNm),
    summary: trunc(clean(raw.plcySprtCn) || clean(raw.plcyExplnCn) || "상세 공고 참조", 90),
    target: trunc([ageText, targetSrc].filter(Boolean).join(" — ") || "상세 공고 참조", 130),
    deadline,
    applyMethod: trunc(clean(raw.plcyAplyMthdCn) || "온라인/방문 신청 (상세 공고 확인)", 80),
    link: clean(raw.aplyUrlAddr) || clean(raw.refUrlAddr1) || "https://www.youthcenter.go.kr",
    eligibility: {
      minAge: minAge && minAge > 0 ? minAge : null,
      maxAge: maxAge && maxAge > 0 && maxAge < 120 ? maxAge : null,
      regions: parseRegions(raw.zipCd, raw.stdgNm),
      maxIncomeRatio: null,   // 소득 조건은 서술형이라 매칭에 사용하지 않음
      employment: parseEmployment(raw),
      maritalStatus: parseMarital(raw),
      requiresChildren: false,
      minHouseholdSize: null,
    },
  };
}

/** 포털 검색 응답(UPPER_SNAKE_CASE) → 공식 API와 같은 camelCase 형태로 정규화 */
function normalizePortalItem(r) {
  const bgng = clean(r.APLY_PRD_BGNG_YMD).replace(/\D/g, "");
  const end = clean(r.APLY_PRD_END_YMD).replace(/\D/g, "");
  return {
    plcyNo: r.DOCID,
    plcyNm: r.PLCY_NM,
    plcyExplnCn: r.PLCY_EXPLN_CN,
    plcySprtCn: r.PLCY_SPRT_CN,
    lclsfNm: r.USER_LCLSF_NM,
    mclsfNm: r.USER_MCLSF_NM,
    sprvsnInstCdNm: r.SPRVSN_INST_CD_NM,
    rgtrUpInstCdNm: r.RGTR_UP_INST_CD_NM,
    operInstCdNm: r.OPER_INST_CD_NM,
    aplyPrdSeCd: r.APLY_PRD_SE_CD,
    aplyYmd: bgng.length === 8 && end.length === 8 ? `${bgng} ~ ${end}` : "",
    bizPrdEndYmd: r.BIZ_PRD_END_YMD,
    plcyAplyMthdCn: r.PLCY_APLY_MTHD_CN,
    aplyUrlAddr: r.APLY_URL_ADDR,
    refUrlAddr1: r.REF_URL_ADDR1,
    addAplyQlfcCndCn: r.ADD_APLY_QLFC_CND_CN,
    sprtTrgtMinAge: r.SPRT_TRGT_MIN_AGE,
    sprtTrgtMaxAge: r.SPRT_TRGT_MAX_AGE,
    zipCd: r.STDG_CD,
    stdgNm: r.STDG_NM,
    empmSttsNm: r.EMPM_STTS_NM,
    mrgSttsNm: r.MRG_STTS_NM,
  };
}

/* ---------------- 데이터 소스 호출 ---------------- */

/** 1순위: 공식 오픈API (키 승인 전에는 필드가 전부 null) */
async function fetchOfficialList(key) {
  if (process.env.YOUTH_API_MOCK) {
    const json = JSON.parse(readFileSync(process.env.YOUTH_API_MOCK, "utf8"));
    return json?.result?.youthPolicyList ?? null;
  }
  if (!key) return null;
  const params = new URLSearchParams({
    apiKeyNm: key, pageNum: "1", pageSize: "100", rtnType: "json",
  });
  const res = await fetch(`${API_URL}?${params}`, { signal: AbortSignal.timeout(30000) });
  if (!res.ok) throw new Error(`getPlcy HTTP ${res.status}`);
  const json = await res.json();
  return json?.result?.youthPolicyList ?? null;
}

/** 2순위: 온통청년 웹 통합검색 JSON (키 불필요, 최신순 정렬) */
async function fetchPortalList() {
  const res = await fetch(PORTAL_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Referer: "https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch",
      "User-Agent": "Mozilla/5.0 PolicyFinder/1.0 (github.com/hyeon-prog/policy-finder)",
    },
    body: JSON.stringify({
      query: "", pageNum: 1, listCount: 100,
      sortFields: "DATE/DESC", searchFields: "all",
    }),
    signal: AbortSignal.timeout(30000),
  });
  if (!res.ok) throw new Error(`portalPolicySearch HTTP ${res.status}`);
  const json = await res.json();
  const list = json?.searchResult?.youthpolicy;
  return Array.isArray(list) ? list.map(normalizePortalItem) : null;
}

/* ---------------- 메인 ---------------- */

const curated = JSON.parse(readFileSync(path.join(ROOT, "data", "curated.json"), "utf8"));
const outPath = path.join(ROOT, "data", "policies.json");
const key = process.env.YOUTH_API_KEY;

await refreshSidoMap();

let rawList = null;
let sourceTag = null;

// 1) 공식 API 시도
try {
  const list = await fetchOfficialList(key);
  if (Array.isArray(list) && list.length && clean(list[0].plcyNm)) {
    rawList = list;
    sourceTag = "youthcenter";
    console.log(`공식 오픈API 사용 — ${list.length}건 수신`);
  } else if (Array.isArray(list) && list.length) {
    console.log("⚠️ 공식 API 응답 필드가 마스킹됨(인증키 승인 대기 추정) — 포털 검색으로 폴백");
  }
} catch (e) {
  console.log(`공식 API 실패(${e.message}) — 포털 검색으로 폴백`);
}

// 2) 포털 검색 폴백
if (!rawList) {
  try {
    const list = await fetchPortalList();
    if (Array.isArray(list) && list.length && clean(list[0].plcyNm)) {
      rawList = list;
      sourceTag = "youthcenter-portal";
      console.log(`포털 통합검색 사용 — ${list.length}건 수신`);
    }
  } catch (e) {
    console.log(`포털 검색 실패(${e.message}) — 큐레이션 데이터만 사용`);
  }
}

// 3) 매핑 · 필터 · 병합
let apiItems = [];
let source = "curated";

if (rawList) {
  const today = todayYmdKst();
  const curatedNames = curated.items.map((it) => normName(it.name));
  const seen = new Set();

  apiItems = rawList
    .map((raw) => mapPolicy(raw, today))
    .filter((it) => it.name)                                   // 불량 행 제외
    .filter((it) => it.open)                                   // 접수 중인 것만
    .filter((it) => {                                          // 큐레이션과 중복 제거
      const n = normName(it.name);
      if (!n || seen.has(n)) return false;
      seen.add(n);
      return !curatedNames.some((c) => n.includes(c) || c.includes(n));
    })
    .slice(0, MAX_API_ITEMS);

  if (apiItems.length) source = `curated+${sourceTag}`;
  console.log(`${rawList.length}건 중 ${apiItems.length}건 채택 (유효·접수중·중복제거 후)`);
}

const output = {
  verifiedAt: curated.verifiedAt,
  generatedAt: new Date().toISOString(),
  source,
  items: [...curated.items, ...apiItems],
};

// 실질 내용이 같으면 파일을 덮어쓰지 않음 (generatedAt만 바뀌는 커밋 방지)
let unchanged = false;
try {
  const prev = JSON.parse(readFileSync(outPath, "utf8"));
  unchanged =
    JSON.stringify({ ...prev, generatedAt: null }) ===
    JSON.stringify({ ...output, generatedAt: null });
} catch { /* 기존 파일이 없거나 손상 → 새로 작성 */ }

if (unchanged) {
  console.log("데이터 내용 변화 없음 — policies.json 유지");
} else {
  writeFileSync(outPath, JSON.stringify(output, null, 2) + "\n");
  console.log(`data/policies.json 생성 완료 — 총 ${output.items.length}건 (source: ${source})`);
}
