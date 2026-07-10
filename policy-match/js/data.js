/**
 * =====================================================================
 * 지원 항목 데이터 (정부정책 + 지자체 프로그램 + 공모전)
 * ---------------------------------------------------------------------
 * ★ 2026-07-10 기준, 각 기관 공고·공식 안내를 웹 검색으로 확인해 작성한
 *   실데이터입니다. 정책은 수시로 바뀌므로 DATA_VERIFIED_AT 이후에는
 *   재검증이 필요합니다. 실서비스에서는 이 파일을 백엔드 API
 *   (예: 온통청년 Open API + 자체 DB)로 교체하세요.
 *
 * type(항목 유형) — 결과 화면의 탭 분류 기준:
 *  - "policy"  : 정부정책 (중앙부처)
 *  - "local"   : 지자체 프로그램 (시/도 단위)
 *  - "contest" : 공모전·대외활동
 *
 * open : 현재(기준일) 신청/접수 가능 여부.
 *        false면 "접수 대기" 그룹으로 분류되고 카드에 마감 표시.
 *
 * eligibility(자격 조건) 스키마:
 *  - minAge / maxAge      : 나이 범위. null이면 제한 없음
 *  - regions              : 지원 지역 배열. ["전국"] 또는 ["서울특별시", ...]
 *  - maxIncomeRatio       : 기준중위소득 상한(%). 참고용 — 개인이 자신의
 *                           중위소득 %를 알기 어려워 매칭에는 사용하지 않음
 *  - employment           : 허용 취업 상태 배열. null이면 무관
 *                           (student|jobseeker|employed|freelancer|self-employed|none)
 *  - maritalStatus        : "married"(기혼만) | "single"(미혼만) | null(무관)
 *  - requiresChildren     : true면 자녀 있는 가구만 해당
 *  - minHouseholdSize     : 최소 가구원 수. null이면 무관
 * =====================================================================
 */
const DATA_VERIFIED_AT = "2026-07-10";

const ITEMS = [
  /* ---------------- 정부정책 (policy) ---------------- */
  {
    id: "youth-monthly-rent",
    type: "policy",
    open: true,
    name: "청년 월세지원 (상시 전환)",
    category: "주거",
    summary: "월 최대 20만 원의 월세를 최장 24개월(총 480만 원) 현금 지원",
    target: "부모와 따로 거주하는 만 19~34세 무주택 청년 — 청년가구 중위소득 60% 이하·원가구 100% 이하, 보증금 8천만 원·월세 60만 원 이하 주택",
    deadline: "상시 신청 (2026년부터 한시사업에서 상시사업으로 전환)",
    applyMethod: "복지로 홈페이지 또는 거주지 행정복지센터 방문 신청",
    link: "https://www.bokjiro.go.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["전국"], maxIncomeRatio: 60, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "national-employment-support",
    type: "policy",
    open: true,
    name: "국민취업지원제도 (I유형)",
    category: "취업",
    summary: "구직촉진수당 월 60만 원 × 6개월 (부양가족 1인당 +10만 원, 최대 +40만 원) + 취업지원 서비스",
    target: "만 15~69세 구직자 중 가구 중위소득 60% 이하·재산 4억 원 이하 — 만 18~34세 청년은 재산 5억 원 이하·취업경험 무관 특례",
    deadline: "상시 신청",
    applyMethod: "고용24(워크넷) 온라인 신청 또는 관할 고용센터 방문",
    link: "https://www.work24.go.kr",
    eligibility: { minAge: 15, maxAge: 69, regions: ["전국"], maxIncomeRatio: 60, employment: ["jobseeker", "none"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "youth-future-savings",
    type: "policy",
    open: true,
    name: "청년미래적금",
    category: "금융",
    summary: "월 최대 50만 원 자유적립 + 정부기여금 6%(우대형 12%) 매칭 + 이자 비과세",
    target: "만 19~34세 소득이 있는 청년 (총급여 7,500만 원 이하 & 가구 중위소득 200% 이하, 맞벌이 2인 가구 250%) — 청년도약계좌 후속 상품(2025.12 신규가입 종료)",
    deadline: "매월 가입신청 기간 운영 (2026-06-22 출시, 취급은행 앱 공고 확인)",
    applyMethod: "취급 은행 모바일 앱에서 비대면 신청",
    link: "https://www.kinfa.or.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["전국"], maxIncomeRatio: 200, employment: ["employed", "freelancer", "self-employed"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "newlywed-jeonse",
    type: "policy",
    open: true,
    name: "신혼·신생아 전세임대주택 (Ⅰ형)",
    category: "주거",
    summary: "전세보증금 최대 1억 4,500만 원(수도권)을 연 1.2~2.2% 저리로 지원",
    target: "혼인 7년 이내(예비·신생아 가구 포함) 무주택 신혼부부 — 도시근로자 월평균소득 70% 이하(배우자 소득 있으면 90%)",
    deadline: "연중 수시 접수",
    applyMethod: "LH 청약플러스 온라인 신청",
    link: "https://apply.lh.or.kr",
    eligibility: { minAge: null, maxAge: null, regions: ["전국"], maxIncomeRatio: 100, employment: null, maritalStatus: "married", requiresChildren: false, minHouseholdSize: 2 }
  },
  {
    id: "seoul-youth-allowance",
    type: "policy",
    open: false,
    name: "서울시 청년수당",
    category: "취업",
    summary: "활동지원금 월 50만 원 × 최대 6개월(최대 300만 원) + 취업역량 프로그램 연계",
    target: "서울 거주 만 19~34세 미취업 청년(최종학력 졸업·수료·중퇴) — 가구 중위소득 150% 이하",
    deadline: "2026년 상반기 모집 마감 (3월·5월 진행) — 다음 공고 확인",
    applyMethod: "청년몽땅정보통(서울청년포털) 온라인 신청",
    link: "https://youth.seoul.go.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["서울특별시"], maxIncomeRatio: 150, employment: ["jobseeker", "none"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "childcare-service",
    type: "policy",
    open: true,
    name: "아이돌봄 서비스 정부지원",
    category: "복지·양육",
    summary: "돌봄 이용요금(시간제 기준 시간당 12,790원)의 10~90%를 소득 구간별 차등 지원",
    target: "12세 이하 자녀 양육 가구 중 중위소득 250% 이하 (맞벌이 가구는 합산소득 25% 감경 판정) — 2026년 소득기준 200%→250% 확대",
    deadline: "상시 신청",
    applyMethod: "아이돌봄서비스 홈페이지 신청 후 읍면동 행정복지센터에서 소득 판정",
    link: "https://idolbom.go.kr",
    eligibility: { minAge: null, maxAge: null, regions: ["전국"], maxIncomeRatio: 250, employment: null, maritalStatus: null, requiresChildren: true, minHouseholdSize: 2 }
  },

  /* ---------------- 지자체 프로그램 (local) ---------------- */
  {
    id: "gg-youth-basic-income",
    type: "local",
    open: true,
    name: "경기도 청년기본소득",
    category: "생활지원",
    summary: "분기별 25만 원(연 최대 100만 원)을 지역화폐로 지급",
    target: "경기도에 3년 이상 계속 거주(또는 합산 10년)한 만 24세 청년 — 성남·고양 등 일부 시군은 미시행이니 거주 시군 확인 필요",
    deadline: "2026년 3분기 접수: 07-01 ~ 08-01 (분기별 신청)",
    applyMethod: "경기도 일자리재단 '잡아바' 온라인 신청",
    link: "https://apply.jobaba.net",
    eligibility: { minAge: 24, maxAge: 24, regions: ["경기도"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "seoul-mind-care",
    type: "local",
    open: true,
    name: "서울시 청년 마음건강 지원사업",
    category: "생활지원",
    summary: "전문 심리검사(KSCL95·TCI) + 맞춤형 심리상담 최대 6회기 무료 지원",
    target: "서울 거주 만 19~39세 청년 (소득·취업 여부 무관, 심리지원이 필요한 청년)",
    deadline: "연 4회 분기별 모집 (2026년 1차 1월 시작 — 청년몽땅정보통 공고 확인)",
    applyMethod: "청년몽땅정보통(서울청년포털) 온라인 신청",
    link: "https://youth.seoul.go.kr",
    eligibility: { minAge: 19, maxAge: 39, regions: ["서울특별시"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "busan-didimdol-card",
    type: "local",
    open: false,
    name: "부산청년 디딤돌카드+ (사회진입 활동비)",
    category: "취업",
    summary: "구직활동비 월 30만 원 × 최대 6개월(180만 원) + 취업 성공 시 30만 원 추가 지급",
    target: "부산 거주 만 18~39세 미취업 청년 (취업역량 강화 프로그램 참여 포함)",
    deadline: "2026년 접수 마감(3/9~3/27 진행) — 매년 3월경 공고",
    applyMethod: "디딤돌카드 홈페이지(youthdidimdol.kr) 온라인 접수",
    link: "https://youthdidimdol.kr",
    eligibility: { minAge: 18, maxAge: 39, regions: ["부산광역시"], maxIncomeRatio: null, employment: ["jobseeker", "none"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },

  /* ---------------- 공모전·대외활동 (contest) ---------------- */
  {
    id: "president-idea-contest",
    type: "contest",
    open: false,
    name: "청년 정책 아이디어 공모전 「내가 대통령이라면」",
    category: "공모전",
    summary: "취업·생활·교육 3대 분야 정책 아이디어 공모 — 총상금 1,300만 원 (7건 선정)",
    target: "만 19~39세 전국 청년 (개인 또는 3인 이하 팀)",
    deadline: "2026-07-08 접수 마감 (국민경제자문회의 주최)",
    applyMethod: "온라인 접수 (2030 자문단 홈페이지 공고 확인)",
    link: "https://www.2030db.go.kr",
    eligibility: { minAge: 19, maxAge: 39, regions: ["전국"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "dive-2026-hackathon",
    type: "contest",
    open: false,
    name: "DIVE 2026 글로벌 데이터 해커톤",
    category: "공모전",
    summary: "부산 벡스코 1박 2일 해커톤(7/25~26) — 데이터·AI 서비스 개발, 팀 2~4인",
    target: "데이터·AI에 관심 있는 청년 개발자·기획자·디자이너 (팀 단위 참가)",
    deadline: "2026-06-24 접수 마감 · 본선 2026-07-25~26",
    applyMethod: "공식 접수 페이지 온라인 등록 (링커리어 공고 참고)",
    link: "https://linkareer.com/activity/325515",
    eligibility: { minAge: null, maxAge: null, regions: ["전국"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  }
];

/**
 * 거주지 드롭다운용 지역 데이터 (시/도 → 시/군/구)
 * 시/군/구는 대표 지역 일부만 수록 — 실서비스에서는
 * 행정표준코드(법정동 코드) API로 대체하세요.
 */
const REGIONS = {
  "서울특별시": ["강남구", "강동구", "관악구", "노원구", "마포구", "서대문구", "성동구", "송파구", "영등포구", "용산구", "은평구", "중구"],
  "부산광역시": ["해운대구", "부산진구", "동래구", "수영구", "사하구", "금정구"],
  "대구광역시": ["수성구", "달서구", "중구", "북구", "동구"],
  "인천광역시": ["연수구", "남동구", "부평구", "서구", "미추홀구"],
  "광주광역시": ["동구", "서구", "남구", "북구", "광산구"],
  "대전광역시": ["유성구", "서구", "중구", "동구", "대덕구"],
  "울산광역시": ["남구", "중구", "동구", "북구", "울주군"],
  "세종특별자치시": ["세종시"],
  "경기도": ["수원시", "성남시", "고양시", "용인시", "부천시", "안양시", "화성시", "평택시", "의정부시"],
  "강원특별자치도": ["춘천시", "원주시", "강릉시", "속초시"],
  "충청북도": ["청주시", "충주시", "제천시"],
  "충청남도": ["천안시", "아산시", "서산시", "공주시"],
  "전북특별자치도": ["전주시", "군산시", "익산시"],
  "전라남도": ["목포시", "여수시", "순천시"],
  "경상북도": ["포항시", "구미시", "경주시", "안동시"],
  "경상남도": ["창원시", "김해시", "진주시", "양산시"],
  "제주특별자치도": ["제주시", "서귀포시"]
};
