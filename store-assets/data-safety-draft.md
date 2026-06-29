# Google Play Data Safety Draft

This is a draft. Final answers must match Play Console wording.

## Data Collected

Personal info

- Email address: collected for account login.
- Name/profile image: collected from Google login when provided.

Financial info

- User-entered holdings, portfolio weights, account settings, tax simulation inputs.
- Purpose: app functionality, portfolio tracking, simulations, alerts.

App activity

- Alert rules and notification preferences.
- Device push token for FCM notifications.

## Data Sharing

- No sale of user data.
- Google OAuth/Firebase/FCM used as service providers.
- Hosting/database infrastructure processes data to provide app functionality.

## Security

- Data sent over HTTPS.
- Account deletion available in app settings.

## Account Deletion

- In-app: Settings > Account > Delete account.
- URL path: `https://moneymilestone.co.kr/settings`

## Ads

- No ads.

## Sensitive Permissions

- Internet.
- Notifications for user-configured alerts.

## Financial Disclaimer

- Informational/calculation tool only.
- Not investment advice.
