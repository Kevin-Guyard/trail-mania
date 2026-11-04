# TrailMania

TrailMania is a training journal for trail running and road running. Keep your workouts on your phone, browse your training history in a calendar, and track your running volume over weeks and months.

## What you can do

- **Record your workouts**: long runs, easy runs, steady runs, threshold sessions, VO2max intervals, and leg strength training.
- **Capture running session details**: terrain, slope, distance, speed, elevation gain, heart rate, time spent in zones Z1 to Z5, perceived effort, and comments, depending on the workout type. Threshold and VO2max sessions also support repetitions and recovery intervals.
- **Browse your training history** in a monthly or weekly calendar, or in a filtered list, then view, edit, or delete a workout.
- **Track your training volume** with weekly and monthly summaries of duration, distance, elevation gain, and time distribution across heart rate zones, both by running session type and overall.
- **Use your journal offline**: workouts are stored on your phone and remain available without a Google account.
- **Back up your data to Google Drive** when the connection is configured and authorized. A backup is requested whenever you add, edit, or delete a workout. The 20 most recent copies are kept in the application's private storage on Drive. If the network is unavailable, retries resume while the application is open and a connection is available.

On first launch, connect to Google Drive or select **“Continuer sans connexion” (Continue without connecting)** to start using the local journal.

## Build the Android APK

The APK is the installation file you copy to an Android phone to install TrailMania.

### Computer requirements

- Install [Python](https://www.python.org/downloads/) **3.14 or later** and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Have an Internet connection to download dependencies and build tools during the first build.
- On Windows, enable **Developer Mode** in system settings if Flutter requests it to create the required symbolic links.

Flet uses Flutter, Java, and the Android SDK to build the application and can download missing tools on the first run. See the [Flet Android build documentation](https://flet.dev/docs/publish/android/) for detailed requirements.

### Commands

Open a terminal in the project directory containing `pyproject.toml`, then run:

```powershell
uv sync
uv run flet build apk
```

The first build may take several minutes. Once it finishes, the installation file is available at:

```text
build/apk/trail-mania.apk
```

Run `uv run flet build apk` again after changing the application to generate a new APK.

## Install the application on your phone

1. Copy `build/apk/trail-mania.apk` to your Android phone, for example using a USB cable.
2. Open the APK using the phone's file manager.
3. If Android prompts you, allow the file manager to install applications from this source.
4. Tap **Install**, then open **TrailMania**.

To update the application, install the new APK over the existing version using the same signing key. Updates preserve your local workouts; uninstalling the application or clearing its data removes them from the phone.

## Enable Google Drive backups (optional)

This setup is only required for Google Drive backups. Complete it before building the APK; the local journal works without it. Google sign-in requires an Android phone with Google Play services.

1. In a Google Cloud project, enable the **Google Drive API**, configure the OAuth consent screen, and add the Google account you want to use as a test user if the application is in testing mode. Declare the `https://www.googleapis.com/auth/drive.appdata` scope.
2. Create an **Android** OAuth client with the package name `com.flet.trail_mania` and the **SHA-1 fingerprint of the certificate used to sign the APK**. Update this configuration if the signing key changes.
3. Also create a **Web application** OAuth client and copy its client ID. The application does not require a client secret.
4. Copy `src/assets/google_drive.example.json` to `src/assets/google_drive.json` and replace the `web_client_id` value with the Web application's client ID. This local file is ignored by Git and will be included in the APK.
5. Build the APK using the commands above, install it, and authorize the Google Drive connection when launching TrailMania.
