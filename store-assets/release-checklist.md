# Play Release Checklist

## Local Build

- [x] JDK 17+ available via Android Studio JBR.
- [x] Upload keystore generated locally.
- [x] `keystore.properties` generated locally.
- [x] Release signing connected in Gradle.
- [x] Release AAB built.
- [x] Upload key backed up outside repo.

## Verification

- [ ] Install release build on physical Android device.
- [ ] Launch app.
- [ ] Google login through system browser.
- [ ] Deep link returns to app.
- [ ] New account consent page: terms/privacy required, push notification optional.
- [ ] Push default OFF when optional consent is unchecked.
- [ ] Logout remains logged out after reload/theme toggle.
- [ ] Push permission prompt.
- [ ] FCM foreground notification.
- [ ] FCM background notification.
- [ ] Account deletion.
- [ ] Back button behavior.
- [ ] Main tabs: Home, Tools, Market, My Assets, Search, Settings.

## Play Console

- [ ] Create app: Money Milestone.
- [ ] Package: `com.moneymilestone.app`.
- [ ] Upload `app-release.aab`.
- [ ] Store listing copy.
- [ ] App icon 512x512.
- [ ] Feature graphic 1024x500.
- [ ] Phone screenshots 2-8. User will handle manually; do not auto-generate.
- [ ] Privacy policy URL.
- [ ] App access instructions if review needs login.
- [ ] Data safety form.
- [ ] Content rating.
- [ ] Target audience.
- [ ] Financial features/disclaimer.

## Files Ready

- AAB: `mobile/android/app/build/outputs/bundle/release/app-release.aab`
- Play icon: `store-assets/play-icon-512.png`
- Feature graphic: `store-assets/feature-graphic-1024x500.png`
- Store listing draft: `store-assets/play-listing-draft.md`
- Data safety draft: `store-assets/data-safety-draft.md`
- App access draft: `store-assets/app-access-instructions.md`

## Still Manual

- Play Console account creation/payment.
- App creation and AAB upload.
- Store form submission.
- Device/login/push verification.
- Closed testing if Google requires it for this developer account.

## Testing Track

- [ ] Internal testing release.
- [ ] If new personal developer account: closed test with 12 testers for 14 days.
- [ ] Production application.
