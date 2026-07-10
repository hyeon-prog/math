/**
 * =====================================================================
 * Mock Data — 지원 항목 예시 데이터 (정부정책 + 지자체 프로그램 + 공모전)
 * ---------------------------------------------------------------------
 * 실제 서비스에서는 이 파일 대신 백엔드 API(예: GET /api/items)로
 * 대체하면 됩니다. 프론트엔드 로직은 그대로 재사용 가능합니다.
 *
 * type(항목 유형) — 결과 화면의 탭 분류 기준:
 *  - "policy"  : 정부정책 (중앙부처)
 *  - "local"   : 지자체 프로그램 (시/도 단위)
 *  - "contest" : 공모전·대외활동
 *
 * eligibility(자격 조건) 스키마:
 *  - minAge / maxAge      : 나이 범위. null이면 제한 없음
 *  - regions              : 지원 지역 배열. ["전국"] 또는 ["서울특별시", ...]
 *  - maxIncomeRatio       : 기준중위소득 상한(%). 참고용 — 개인이 자신의
 *                           중위소득 %를 알기 어려워 현재 매칭에는 사용하지 않음
 *  - employment           : 허용 취업 상태 배열. null이면 무관
 *                           (student|jobseeker|employed|freelancer|self-employed|none)
 *  - maritalStatus        : "married"(기혼만) | "single"(미혼만) | null(무관)
 *  - requiresChildren     : true면 자녀 있는 가구만 해당
 *  - minHouseholdSize     : 최소 가구원 수. null이면 무관
 * =====================================================================
 */
const ITEMS = [
  /* ---------------- 정부정책 (policy) ---------------- */
  {
    id: "youth-monthly-rent",
    type: "policy",
    name: "청년 월세 특별지원",
    category: "주거",
    summary: "월 최대 20만 원의 월세를 최장 12개월(총 240만 원) 현금 지원",
    target: "부모와 따로 거주하는 만 19~34세 무주택 청년 (청년가구 중위소득 60% 이하)",
    deadline: "상시 신청 (예산 소진 시 조기 마감)",
    applyMethod: "복지로 홈페이지 또는 거주지 행정복지센터 방문 신청",
    link: "https://www.bokjiro.go.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["전국"], maxIncomeRatio: 60, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "national-employment-support",
    type: "policy",
    name: "국민취업지원제도 (I유형)",
    category: "취업",
    summary: "구직촉진수당 월 50만 원 × 6개월 + 맞춤형 취업지원 서비스 제공",
    target: "만 15~69세 구직자 중 가구 중위소득 60% 이하, 재산 4억 원 이하",
    deadline: "상시 신청",
    applyMethod: "고용24(워크넷) 온라인 신청 또는 관할 고용센터 방문",
    link: "https://www.work24.go.kr",
    eligibility: { minAge: 15, maxAge: 69, regions: ["전국"], maxIncomeRatio: 60, employment: ["jobseeker", "none"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "youth-leap-account",
    type: "policy",
    name: "청년도약계좌",
    category: "금융",
    summary: "5년 만기 시 최대 약 5,000만 원 목돈 마련 (정부기여금 + 비과세 혜택)",
    target: "만 19~34세 소득이 있는 청년 (가구 중위소득 180% 이하)",
    deadline: "매월 초 신청 기간 운영 (은행 앱 공고 확인)",
    applyMethod: "취급 은행 모바일 앱에서 비대면 신청",
    link: "https://ylaccount.kinfa.or.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["전국"], maxIncomeRatio: 180, employment: ["employed", "freelancer", "self-employed"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "newlywed-jeonse",
    type: "policy",
    name: "신혼부부 전세임대주택 (I형)",
    category: "주거",
    summary: "전세보증금 최대 1억 4,500만 원(수도권 기준)을 연 1~2%대 저리로 지원",
    target: "혼인 7년 이내 무주택 신혼부부 (가구 중위소득 100% 이하)",
    deadline: "2026-12-31까지 (연중 수시 접수)",
    applyMethod: "LH 청약플러스 온라인 신청",
    link: "https://apply.lh.or.kr",
    eligibility: { minAge: null, maxAge: null, regions: ["전국"], maxIncomeRatio: 100, employment: null, maritalStatus: "married", requiresChildren: false, minHouseholdSize: 2 }
  },
  {
    id: "seoul-youth-allowance",
    type: "policy",
    name: "서울시 청년수당",
    category: "취업",
    summary: "활동지원금 월 50만 원 × 최대 6개월 지급 + 취업역량 프로그램 연계",
    target: "서울 거주 만 19~34세 미취업 청년 (중위소득 150% 이하)",
    deadline: "연 1~2회 모집 (서울청년포털 공고 확인)",
    applyMethod: "청년몽땅정보통(서울청년포털) 온라인 신청",
    link: "https://youth.seoul.go.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["서울특별시"], maxIncomeRatio: 150, employment: ["jobseeker", "none"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "childcare-service",
    type: "policy",
    name: "아이돌봄 서비스 정부지원",
    category: "복지·양육",
    summary: "아이돌보미 서비스 이용요금의 최대 85%까지 소득 구간별 차등 지원",
    target: "12세 이하 자녀 양육 가구 중 중위소득 150% 이하 (맞벌이 등 양육 공백 가구)",
    deadline: "상시 신청",
    applyMethod: "아이돌봄서비스 홈페이지 신청 후 읍면동 행정복지센터에서 소득 판정",
    link: "https://idolbom.go.kr",
    eligibility: { minAge: null, maxAge: null, regions: ["전국"], maxIncomeRatio: 150, employment: null, maritalStatus: null, requiresChildren: true, minHouseholdSize: 2 }
  },

  /* ---------------- 지자체 프로그램 (local) ---------------- */
  {
    id: "gg-youth-basic-income",
    type: "local",
    name: "경기도 청년기본소득",
    category: "생활지원",
    summary: "분기별 25만 원(연 최대 100만 원)을 지역화폐로 지급",
    target: "경기도에 3년 이상 계속 거주(또는 합산 10년)한 만 24세 청년",
    deadline: "분기별 신청 (3분기: 2026-07-01 ~ 2026-08-01)",
    applyMethod: "경기도 일자리재단 '잡아바' 온라인 신청",
    link: "https://apply.jobaba.net",
    eligibility: { minAge: 24, maxAge: 24, regions: ["경기도"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "seoul-mind-care",
    type: "local",
    name: "서울시 청년 마음건강 지원사업",
    category: "생활지원",
    summary: "전문 심리상담 6~10회 무료 지원 (1인 최대 약 70만 원 상당)",
    target: "서울 거주 만 19~39세 청년 (소득·취업 여부 무관)",
    deadline: "분기별 모집 (서울청년포털 공고 확인)",
    applyMethod: "청년몽땅정보통(서울청년포털) 온라인 신청",
    link: "https://youth.seoul.go.kr",
    eligibility: { minAge: 19, maxAge: 39, regions: ["서울특별시"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "busan-didimdol-card",
    type: "local",
    name: "부산청년 디딤돌카드+",
    category: "취업",
    summary: "구직활동비 월 50만 원 × 6개월을 카드 포인트로 지원",
    target: "부산 거주 만 18~34세 미취업 청년 (기준중위소득 120% 이하)",
    deadline: "상·하반기 모집 (하반기: 2026-09 공고 예정)",
    applyMethod: "부산청년플랫폼 온라인 신청",
    link: "https://young.busan.go.kr",
    eligibility: { minAge: 18, maxAge: 34, regions: ["부산광역시"], maxIncomeRatio: 120, employment: ["jobseeker", "none"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },

  /* ---------------- 공모전·대외활동 (contest) ---------------- */
  {
    id: "innovation-idea-contest",
    type: "contest",
    name: "정부혁신 국민참여 아이디어 공모전",
    category: "공모전",
    summary: "대상 500만 원 등 총상금 2,000만 원 · 우수 제안은 실제 정책에 반영",
    target: "대한민국 국민 누구나 (개인 또는 팀, 나이 제한 없음)",
    deadline: "2026-08-31 접수 마감",
    applyMethod: "혁신24 홈페이지 온라인 접수",
    link: "https://www.innovation.go.kr",
    eligibility: { minAge: null, maxAge: null, regions: ["전국"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "youthday-content-contest",
    type: "contest",
    name: "청년의 날 기념 콘텐츠 공모전",
    category: "공모전",
    summary: "영상·카드뉴스 부문별 시상, 총상금 1,000만 원 (최우수 300만 원)",
    target: "만 19~39세 청년 누구나 (개인 또는 3인 이내 팀)",
    deadline: "2026-09-15 접수 마감",
    applyMethod: "온통청년 홈페이지 공고 페이지에서 온라인 접수",
    link: "https://www.youthcenter.go.kr",
    eligibility: { minAge: 19, maxAge: 39, regions: ["전국"], maxIncomeRatio: null, employment: null, maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  },
  {
    id: "local-problem-hackathon",
    type: "contest",
    name: "지역사회 문제해결 청년 해커톤",
    category: "공모전",
    summary: "총상금 1,500만 원 + 우수팀 창업지원 프로그램 연계 (2박 3일 합숙)",
    target: "만 19~34세 대학생 및 청년 구직자 (팀 단위 참가)",
    deadline: "2026-07-25 접수 마감",
    applyMethod: "K-스타트업 홈페이지 공고 페이지에서 팀 단위 접수",
    link: "https://www.k-startup.go.kr",
    eligibility: { minAge: 19, maxAge: 34, regions: ["전국"], maxIncomeRatio: null, employment: ["student", "jobseeker"], maritalStatus: null, requiresChildren: false, minHouseholdSize: null }
  }
];

/**
 * 거주지 드롭다운용 지역 데이터 (시/도 → 시/군/구)
 * 프로토타입이므로 시/군/구는 대표 지역 일부만 수록했습니다.
 * 실제 서비스에서는 행정표준코드(법정동 코드) API로 대체하세요.
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
