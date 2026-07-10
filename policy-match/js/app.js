/**
 * =====================================================================
 * app.js — 폼 처리 · 매칭 알고리즘 · 유형별 탭 · 결과 렌더링
 * 의존성: js/data.js 의 전역 상수 ITEMS, REGIONS
 * =====================================================================
 */

/* ------------------------------------------------------------------ *
 * 0. 상수 & 유틸
 * ------------------------------------------------------------------ */

// 관심도 기반 추천 커트라인: 전체 조건 중 60% 이상 충족하면 "관심 항목"으로 노출
const INTEREST_THRESHOLD = 0.6;

// 결과 화면 탭 정의 (data.js 의 type 필드와 매핑)
const TYPES = [
  { key: "all", label: "전체" },
  { key: "policy", label: "정부정책" },
  { key: "local", label: "지자체 프로그램" },
  { key: "contest", label: "공모전·대외활동" },
];

// 카드에 표시할 유형 라벨 (짧은 버전)
const TYPE_LABELS = { policy: "정부정책", local: "지자체", contest: "공모전" };

// 카테고리별 태그 색상 (Tailwind 클래스)
const CATEGORY_STYLES = {
  "주거":      "bg-blue-100 text-blue-700",
  "취업":      "bg-emerald-100 text-emerald-700",
  "금융":      "bg-amber-100 text-amber-800",
  "복지·양육": "bg-rose-100 text-rose-700",
  "생활지원":  "bg-teal-100 text-teal-700",
  "공모전":    "bg-violet-100 text-violet-700",
};

// 취업 상태 코드 → 한글 라벨 (미충족 사유 표시에 사용)
const EMPLOYMENT_LABELS = {
  student: "학생", jobseeker: "구직자", employed: "재직자",
  freelancer: "프리랜서", "self-employed": "자영업자", none: "무직/기타",
};

const $ = (selector) => document.querySelector(selector);

// 화면 상태: 마지막 매칭 결과 + 현재 선택된 탭
let lastMatch = null;
let activeType = "all";

/* ------------------------------------------------------------------ *
 * 1. 거주지 드롭다운 초기화 (시/도 → 시/군/구 연동)
 * ------------------------------------------------------------------ */

function initRegionSelects() {
  const sidoSelect = $("#sido");
  const sigunguSelect = $("#sigungu");

  Object.keys(REGIONS).forEach((sido) => sidoSelect.add(new Option(sido, sido)));

  sidoSelect.addEventListener("change", () => {
    const districts = REGIONS[sidoSelect.value] || [];
    sigunguSelect.innerHTML = "";
    sigunguSelect.disabled = districts.length === 0;
    sigunguSelect.add(new Option(districts.length ? "선택하세요" : "시/도를 먼저 선택하세요", ""));
    districts.forEach((gu) => sigunguSelect.add(new Option(gu, gu)));
  });
}

/* ------------------------------------------------------------------ *
 * 2. 폼 입력값 → 사용자 프로필 객체로 변환
 * ------------------------------------------------------------------ */

function buildUserProfile(form) {
  const data = new FormData(form);
  const family = data.get("family"); // single | married | married-child | single-parent

  return {
    age: Number(data.get("age")),
    sido: data.get("sido"),                    // 예: "서울특별시"
    sigungu: data.get("sigungu"),              // 예: "마포구" (현재 매칭은 시/도 단위, 향후 확장용)
    householdSize: Number(data.get("household")),
    employment: data.get("employment"),
    married: family === "married" || family === "married-child",
    hasChildren: family === "married-child" || family === "single-parent",
  };
}

/* ------------------------------------------------------------------ *
 * 3. ★ 핵심: 매칭 알고리즘
 * ------------------------------------------------------------------ *
 * 항목마다 "실제로 요구하는 조건"만 골라 검사(checks)하고,
 *   - perfect : 모든 조건 충족 → 맞춤 항목
 *   - score   : 충족 비율 (관심도 점수, 0~1)
 * 을 계산합니다. 조건이 없는 항목(null)은 검사 대상에서 제외하므로
 * 점수가 불리하게 희석되지 않습니다. (조건이 하나도 없으면 전 국민 대상)
 * ------------------------------------------------------------------ */

function evaluateItem(user, item) {
  const e = item.eligibility;
  const checks = []; // { label: 조건명, pass: 충족 여부, hint: 미충족 사유 }

  // ① 나이 조건
  if (e.minAge !== null || e.maxAge !== null) {
    const pass =
      (e.minAge === null || user.age >= e.minAge) &&
      (e.maxAge === null || user.age <= e.maxAge);
    checks.push({
      label: "나이",
      pass,
      hint: `만 ${e.minAge ?? "제한없음"}~${e.maxAge ?? "제한없음"}세 대상`,
    });
  }

  // ② 거주지 조건 ("전국"이면 무조건 통과)
  if (!e.regions.includes("전국")) {
    checks.push({
      label: "거주지",
      pass: e.regions.includes(user.sido),
      hint: `${e.regions.join(", ")} 거주자 대상`,
    });
  }

  // ※ 소득 조건은 매칭에서 제외 — 개인이 자신의 중위소득 %를 알기 어려워
  //   입력받지 않고, 카드의 '지원 대상' 문구로만 안내합니다. (e.maxIncomeRatio는 참고용)

  // ③ 취업 상태 조건
  if (e.employment !== null) {
    checks.push({
      label: "취업 상태",
      pass: e.employment.includes(user.employment),
      hint: `${e.employment.map((c) => EMPLOYMENT_LABELS[c]).join("·")} 대상`,
    });
  }

  // ④ 혼인 상태 조건
  if (e.maritalStatus !== null) {
    checks.push({
      label: "혼인 상태",
      pass: (e.maritalStatus === "married") === user.married,
      hint: e.maritalStatus === "married" ? "기혼 가구 대상" : "미혼 대상",
    });
  }

  // ⑤ 자녀 조건
  if (e.requiresChildren) {
    checks.push({ label: "자녀", pass: user.hasChildren, hint: "자녀 양육 가구 대상" });
  }

  // ⑥ 가구원 수 조건
  if (e.minHouseholdSize !== null) {
    checks.push({
      label: "가구원 수",
      pass: user.householdSize >= e.minHouseholdSize,
      hint: `${e.minHouseholdSize}인 이상 가구 대상`,
    });
  }

  const passedCount = checks.filter((c) => c.pass).length;

  return {
    item,
    checks,
    score: checks.length === 0 ? 1 : passedCount / checks.length,
    perfect: passedCount === checks.length,
    failed: checks.filter((c) => !c.pass),
  };
}

/**
 * 전체 항목을 평가한 뒤 두 그룹으로 분류
 *  - perfect : 모든 조건 충족 (신청 가능)
 *  - partial : 60% 이상 충족 (관심도 기반 추천, 점수 내림차순 정렬)
 */
function matchItems(user, items) {
  const results = items.map((it) => evaluateItem(user, it));

  return {
    perfect: results.filter((r) => r.perfect),
    partial: results
      .filter((r) => !r.perfect && r.score >= INTEREST_THRESHOLD)
      .sort((a, b) => b.score - a.score),
  };
}

/* ------------------------------------------------------------------ *
 * 4. 유형별 탭 (전체 / 정부정책 / 지자체 / 공모전)
 * ------------------------------------------------------------------ */

/** 특정 탭에 표시될 결과만 필터링 */
function filterByType(results, typeKey) {
  return typeKey === "all" ? results : results.filter((r) => r.item.type === typeKey);
}

/** 탭별 매칭 건수 (맞춤 + 관심 합계) — 탭 배지에 표시 */
function countByType(typeKey) {
  return (
    filterByType(lastMatch.perfect, typeKey).length +
    filterByType(lastMatch.partial, typeKey).length
  );
}

function renderTabs() {
  const tabsEl = $("#type-tabs");
  tabsEl.innerHTML = TYPES.map((t) => {
    const selected = t.key === activeType;
    return `
      <button type="button" role="tab" id="tab-${t.key}" data-type="${t.key}"
              aria-selected="${selected}" aria-controls="result-panel"
              class="px-3.5 py-2.5 text-sm font-bold -mb-px border-b-2 transition-colors
                     ${selected ? "text-blue-600 border-blue-600" : "text-slate-500 border-transparent hover:text-slate-700"}">
        ${t.label}
        <span class="ml-1 inline-block text-[11px] font-bold px-1.5 py-0.5 rounded-full align-middle
                     ${selected ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-500"}">${countByType(t.key)}</span>
      </button>`;
  }).join("");

  $("#result-panel").setAttribute("aria-labelledby", `tab-${activeType}`);
}

function selectTab(typeKey, { focus = false } = {}) {
  activeType = typeKey;
  renderTabs();
  renderLists();
  if (focus) $(`#tab-${typeKey}`)?.focus();
}

function initTabs() {
  const tabsEl = $("#type-tabs");

  // 클릭으로 탭 전환
  tabsEl.addEventListener("click", (event) => {
    const btn = event.target.closest("[role='tab']");
    if (btn) selectTab(btn.dataset.type);
  });

  // 접근성: 좌우 방향키로 탭 이동
  tabsEl.addEventListener("keydown", (event) => {
    const idx = TYPES.findIndex((t) => t.key === activeType);
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectTab(TYPES[(idx + 1) % TYPES.length].key, { focus: true });
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectTab(TYPES[(idx - 1 + TYPES.length) % TYPES.length].key, { focus: true });
    }
  });
}

/* ------------------------------------------------------------------ *
 * 5. 결과 렌더링
 * ------------------------------------------------------------------ */

/** XSS 방지용 이스케이프 (Mock 데이터가 API 응답으로 바뀔 때를 대비) */
function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
  );
}

/** 항목 1건 → 카드 HTML */
function renderCard(result, { isPartial }) {
  const p = result.item;
  const tagStyle = CATEGORY_STYLES[p.category] || "bg-slate-100 text-slate-600";
  const regionLabel = p.eligibility.regions.includes("전국") ? "전국" : p.eligibility.regions.join("·");

  // 관심 항목일 때만: 미충족 조건 배지 표시
  const failedBadges = isPartial
    ? `<div class="mt-3 flex flex-wrap gap-1.5">
         ${result.failed
           .map(
             (c) => `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-red-50 text-red-600 border border-red-200 rounded-full px-2.5 py-1"
                           title="${escapeHtml(c.hint)}">✕ ${escapeHtml(c.label)} 미충족 <span class="font-normal text-red-400">(${escapeHtml(c.hint)})</span></span>`
           )
           .join("")}
       </div>`
    : "";

  return `
    <article class="policy-card bg-white rounded-2xl border ${isPartial ? "border-amber-200" : "border-emerald-200"} shadow-sm p-5 flex flex-col">
      <!-- 태그 영역: 유형 / 카테고리 / 지역 / 충족 상태 -->
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="text-xs font-semibold px-2.5 py-1 rounded-full border border-slate-200 text-slate-500">${escapeHtml(TYPE_LABELS[p.type])}</span>
        <span class="text-xs font-bold px-2.5 py-1 rounded-full ${tagStyle}">${escapeHtml(p.category)}</span>
        <span class="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-500">📍 ${escapeHtml(regionLabel)}</span>
        ${
          isPartial
            ? `<span class="ml-auto text-xs font-bold text-amber-600">조건 충족률 ${Math.round(result.score * 100)}%</span>`
            : `<span class="ml-auto text-xs font-bold text-emerald-600">✓ 조건 충족</span>`
        }
      </div>

      <!-- 항목명 & 지원 내용 -->
      <h4 class="mt-3 text-lg font-bold leading-snug">${escapeHtml(p.name)}</h4>
      <p class="mt-1.5 text-sm text-blue-700 font-semibold">${escapeHtml(p.summary)}</p>

      <!-- 상세 정보 -->
      <dl class="mt-3 space-y-1.5 text-sm text-slate-600 flex-1">
        <div class="flex gap-2"><dt class="shrink-0 w-16 font-semibold text-slate-400">지원 대상</dt><dd>${escapeHtml(p.target)}</dd></div>
        <div class="flex gap-2"><dt class="shrink-0 w-16 font-semibold text-slate-400">신청 기한</dt><dd>${escapeHtml(p.deadline)}</dd></div>
        <div class="flex gap-2"><dt class="shrink-0 w-16 font-semibold text-slate-400">신청 방법</dt><dd>${escapeHtml(p.applyMethod)}</dd></div>
      </dl>

      ${failedBadges}

      <!-- 상세 링크 -->
      <a href="${escapeHtml(p.link)}" target="_blank" rel="noopener noreferrer"
         class="mt-4 inline-flex items-center justify-center gap-1 w-full text-sm font-bold py-2.5 rounded-xl transition-colors
                ${isPartial ? "bg-amber-50 hover:bg-amber-100 text-amber-700" : "bg-emerald-600 hover:bg-emerald-700 text-white"}"
         aria-label="${escapeHtml(p.name)} 상세 안내 새 창에서 보기">
        자세히 보기 ↗
      </a>
    </article>`;
}

/** 현재 선택된 탭 기준으로 목록을 다시 그림 */
function renderLists() {
  const perfect = filterByType(lastMatch.perfect, activeType);
  const partial = filterByType(lastMatch.partial, activeType);

  $("#perfect-section").classList.toggle("hidden", perfect.length === 0);
  $("#perfect-list").innerHTML = perfect.map((r) => renderCard(r, { isPartial: false })).join("");

  $("#partial-section").classList.toggle("hidden", partial.length === 0);
  $("#partial-list").innerHTML = partial.map((r) => renderCard(r, { isPartial: true })).join("");

  $("#empty-state").classList.toggle("hidden", perfect.length + partial.length > 0);
}

/** 검색 직후 결과 영역 전체를 초기화하고 표시 */
function renderResults() {
  $("#results").classList.remove("hidden");
  $("#result-summary").textContent =
    `전체 ${ITEMS.length}개 항목 중 바로 신청 가능한 항목 ${lastMatch.perfect.length}건, ` +
    `관심 가질 만한 항목 ${lastMatch.partial.length}건을 찾았습니다.`;

  renderTabs();
  renderLists();
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ------------------------------------------------------------------ *
 * 6. 이벤트 바인딩 (제출 / 초기화)
 * ------------------------------------------------------------------ */

function initForm() {
  const form = $("#user-form");
  const errorEl = $("#form-error");

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!form.checkValidity()) {
      errorEl.textContent = "⚠️ 모든 항목을 입력해 주세요. 빈 항목이 있습니다.";
      errorEl.classList.remove("hidden");
      form.querySelector(":invalid")?.focus();
      return;
    }
    errorEl.classList.add("hidden");

    lastMatch = matchItems(buildUserProfile(form), ITEMS);
    activeType = "all"; // 새 검색은 항상 '전체' 탭부터
    renderResults();
  });

  form.addEventListener("reset", () => {
    errorEl.classList.add("hidden");
    $("#results").classList.add("hidden");
    lastMatch = null;
    activeType = "all";
    const sigunguSelect = $("#sigungu");
    sigunguSelect.innerHTML = '<option value="">시/도를 먼저 선택하세요</option>';
    sigunguSelect.disabled = true;
  });
}

/* ------------------------------------------------------------------ *
 * 7. 앱 시작
 * ------------------------------------------------------------------ */
initRegionSelects();
initTabs();
initForm();
