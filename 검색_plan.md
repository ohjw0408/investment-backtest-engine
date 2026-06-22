# 검색 유입(SEO) 계획

> mysnowball.kr 벤치마크 → 도구 페이지 검색 유입이 목표. 시작 2026-06-22.
> 핵심 개념: **색인(검색 등장 자격, sitemap 제출 = 자동/며칠~2주) ≠ 상위노출(랭킹, 콘텐츠·권위·시간 = 수주~수개월).**

---

## ✅ 완료

- **도메인**: moneymilestone.co.kr (hosting.kr, 개인명의) 이전 완료. TLS(Let's Encrypt A+)·http→https·www→non-www. 구 duckdns 정리.
- **canonical 단일화**: 서버 `.env` `CANONICAL_HOST=moneymilestone.co.kr` → www/IP로 와도 canonical=non-www 고정.
- **SEO 인프라**(commit 9ff40c1):
  - `/robots.txt` (개인/API/auth Disallow + Sitemap 링크)
  - `/sitemap.xml` (공개 11페이지: 홈·calculator·backtest·risk-return·simple·dividend-target·retirement·macro·calendar·terms·privacy). 라우트 = app.py.
  - base.html: canonical·meta description(`{% block meta_desc %}`)·og·twitter
  - 페이지별 meta_desc: 홈 + 6개 도구 (키워드 타겟 스니펫)
- **Google Search Console**: URL접두어 `https://moneymilestone.co.kr` 소유확인 완료(meta 태그 base.html, commit 5af4c39, 프로드 라이브 확인).
- (UX) 홈 persona 6카드 — 진입 동선 개선.

## ⏳ 진행 중

- **Google**: 소유확인 통과. 현재 GSC 데이터 처리중(며칠). **→ Sitemaps에 `sitemap.xml` 즉시 제출**(처리중이어도 가능, 막지 않음). 제출 후 며칠~2주 색인 시작.

## ☐ 다음 (우선순위)

1. **네이버 서치어드바이저** 등록 — searchadvisor.naver.com, HTML 태그 받아 base.html에 추가(google 태그 옆). **국내 유입 최대라 중요.** + sitemap 제출.
2. **Bing Webmaster** — "Import from GSC"로 한방, 또는 msvalidate.01 메타. + sitemap.
3. **★ 도구 페이지 서버렌더 콘텐츠 (랭킹 본체)** — 현재 도구 페이지는 JS 렌더라 본문 텍스트 빈약 → 구글이 주제 약하게 인식. 각 페이지에 **서버 HTML `<h1>` + 설명 문단**(키워드 자연 포함) 추가. 예: 배당금 계산기 → `<h1>배당금 계산기</h1><p>목표 배당수익을 받으려면 얼마를 투자해야 하는지 역산…</p>`. "배당금 계산기" 등 경쟁어 상위노출의 핵심.
4. **FAQ 섹션** (각 도구 하단) — 롱테일 검색 흡수 + JSON-LD FAQPage 리치결과.
5. **쿼리파라미터 프리필** — `/dividend-target?stock=SCHD&yield=3.34…` 식 결과 공유 딥링크(스노우볼식). 백링크·바이럴.
6. **백링크 + 시간** — 외부 링크 = 권위. 통제 어려움, 콘텐츠로 유도.

## 기대치 (정직)

- **브랜드어**("머니마일스톤"/"Money Milestone"): 경쟁 없음 → 색인되면 곧 1등.
- **일반 경쟁어**("배당금 계산기"·"자산배분투자"·"포트폴리오 백테스트"): 색인은 되지만 신생 사이트(권위 0)라 상위노출은 #3 콘텐츠 작업 + 수주~수개월 + 백링크 필요.

## 참고 (구현 위치)

- sitemap/robots 라우트·`CANONICAL_HOST`·canonical context = `app.py`
- 페이지별 메타 = 각 템플릿 `{% block meta_desc %}`, 공통 = `base.html` head
- 소유확인 태그 = `base.html` head (`google-site-verification` 등 여기 모음)
- 배포 = push(main) → GitHub Actions. canonical은 서버 `.env` env.
