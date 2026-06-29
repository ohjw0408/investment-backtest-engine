# Google Play Release Plan

Updated: 2026-06-29

## Current Status

Ready locally:

- Release AAB built: `mobile/android/app/build/outputs/bundle/release/app-release.aab`
- Upload key generated and backed up by owner.
- Release signing connected in `mobile/android/app/build.gradle`.
- Java/Gradle build works through Android Studio JBR.
- Play icon ready: `store-assets/play-icon-512.png`
- Feature graphic ready: `store-assets/feature-graphic-1024x500.png`
- Store listing draft ready: `store-assets/play-listing-draft.md`
- Data safety draft ready: `store-assets/data-safety-draft.md`
- Reviewer access draft ready: `store-assets/app-access-instructions.md`
- High-resolution logo applied to Android icons and splash images.
- Push notification consent is server-side and default OFF.
- Android OAuth app handoff uses a package-scoped intent to reduce wrong app chooser issues.

Related files:

- Build/run notes: `mobile/README.md`
- Release checklist: `store-assets/release-checklist.md`
- Legal/security prelaunch plan: `LAUNCH_LEGAL_SECURITY_PLAN.md`

## Next Step

Phase 1 is next: physical Android device verification.

Do this before Play Console upload because the biggest launch risk is not the AAB file. The biggest risk is Google login/deep-link behavior inside the Android WebView.

Verify on a real Android phone:

- Install release build.
- Launch app.
- Google login opens and completes.
- OAuth deep link returns to app.
- New account consent page shows required terms/privacy and optional push notification consent.
- If optional push consent is unchecked, no push token is registered and no notification can be sent.
- If optional push consent is checked, Android notification permission can be granted and push token registers.
- Home, Tools, Market, My Assets, Search, Settings open.
- Add/delete a sample holding.
- Logout stays logged out after reload/theme toggle.
- Account deletion works.
- Back button behavior is acceptable.
- Push permission prompt appears when expected.
- Push default is OFF until explicit optional consent.
- Foreground/background push behavior if FCM is configured.

## Phase 2: Play Console Setup

Owner-only/manual:

- Create Google Play Console developer account.
- Use personal account for fastest launch unless Google requires organization account.
- Create app:
  - App name: Money Milestone
  - Default language: Korean or English, decide in Console.
  - App/package id: `com.moneymilestone.app`
  - Category: Finance
  - Ads: No
- Enable Play App Signing.
- Upload `app-release.aab` to Internal testing first.

## Phase 3: Store Forms

Use prepared files:

- Store listing: `store-assets/play-listing-draft.md`
- Data safety: `store-assets/data-safety-draft.md`
- App access: `store-assets/app-access-instructions.md`
- Icon: `store-assets/play-icon-512.png`
- Feature graphic: `store-assets/feature-graphic-1024x500.png`

Manual inputs still required:

- Phone screenshots, 2-8. Owner handles manually. Do not auto-generate.
- Privacy policy URL: `https://moneymilestone.co.kr/privacy`
- Terms URL: `https://moneymilestone.co.kr/terms`
- Content rating questionnaire.
- Target audience.
- Financial features declaration.
- App access/test account details if Google asks.

Financial declaration stance:

- Informational portfolio and simulation tool.
- Not investment advice.
- Not brokerage.
- Not trading execution.
- Not custody.
- Not lending.
- Not crypto exchange.

## Phase 4: Testing Track

- Start with Internal testing.
- If this is a new personal developer account, Google may require closed testing with 12 testers for 14 days before production.
- Fix issues found in testing.
- Submit production release after testing gate clears.

## Recommended Before Production

- Add public account deletion instruction page, e.g. `/account-deletion`.
- Re-check finance disclaimers on store listing and in app.
- Verify privacy policy mentions Google OAuth, Firebase/FCM, holdings, portfolio data, and account deletion.
- Consider `android:allowBackup="false"` for app data backup risk.
- Consider native Android back-button handling through `@capacitor/app`.
- Consider organization account + D-U-N-S later if Google classifies the app as a regulated financial service.

## Do Not Lose

These files are required to update the app later and are intentionally not committed:

- `mobile/moneymilestone-upload.jks`
- `mobile/android/keystore.properties`

If either is lost, future updates can become painful or impossible without Google support.
