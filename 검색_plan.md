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

## ✅ 추가 완료 (2026-06-22)

- **검색엔진 4사 등록**: Google(소유확인+sitemap 제출)·Naver(소유확인+sitemap+웹페이지수집)·Daum(검색등록 URL 제출)·Bing(GSC import). 소유확인 meta=base.html(google·naver). Google+Naver=한국 ~90%가 본진.
- **도구페이지 서버렌더 SEO 콘텐츠 1차**: 6개 도구에 h1(키워드 포함)+키워드 풍부 설명문단을 **서버 HTML**로(JS 아님). simple h2→h1 승격, risk_return은 h1+설명을 **로그인벽 위 공통으로** 빼서 Googlebot(비로그인) 크롤 가능. 페이지당 h1 1개. Playwright 검증(렌더·콘솔0).

## ⏳ 대기 (자동)

- 색인: sitemap 제출됨 → 며칠~2주 크롤·색인. `site:moneymilestone.co.kr`로 확인. GSC URL검사 "색인 생성 요청"으로 당기기 가능.

## ☐ 다음 (우선순위)

1. **FAQ 섹션** (각 도구 하단) — 롱테일 검색 흡수 + JSON-LD FAQPage 리치결과.
2. **쿼리파라미터 프리필** — `/dividend-target?stock=SCHD&yield=3.34…` 식 결과 공유 딥링크(스노우볼식). 백링크·바이럴.
3. **백링크 + 시간** — 외부 링크 = 권위. 통제 어려움, 콘텐츠로 유도.
4. (선택) 도구페이지 본문 콘텐츠 더 확장.

## 기대치 (정직)

- **브랜드어**("머니마일스톤"/"Money Milestone"): 경쟁 없음 → 색인되면 곧 1등.
- **일반 경쟁어**("배당금 계산기"·"자산배분투자"·"포트폴리오 백테스트"): 색인은 되지만 신생 사이트(권위 0)라 상위노출은 #3 콘텐츠 작업 + 수주~수개월 + 백링크 필요.

## 참고 (구현 위치)

- sitemap/robots 라우트·`CANONICAL_HOST`·canonical context = `app.py`
- 페이지별 메타 = 각 템플릿 `{% block meta_desc %}`, 공통 = `base.html` head
- 소유확인 태그 = `base.html` head (`google-site-verification` 등 여기 모음)
- 배포 = push(main) → GitHub Actions. canonical은 서버 `.env` env.
