import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_sign_in_platform_interface/google_sign_in_platform_interface.dart';
import 'package:trail_mania_drive/trail_mania_drive.dart';

class TestControl implements Control {
  late InvokeControlMethodCallback callNative;

  @override
  void addInvokeMethodListener(InvokeControlMethodCallback listener) {
    callNative = listener;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeGoogle extends GoogleSignInPlatform {
  bool canceled = false;
  bool denied = false;
  bool granted = true;
  GoogleSignInExceptionCode? lightweightError;
  int authentications = 0;

  @override
  Future<void> init(InitParameters params) async {}

  @override
  Future<AuthenticationResults?> attemptLightweightAuthentication(
      AttemptLightweightAuthenticationParameters params) async {
    if (lightweightError != null) {
      throw GoogleSignInException(code: lightweightError!);
    }
    return const AuthenticationResults(
      user: GoogleSignInUserData(email: 'runner@example.com', id: 'runner'),
      authenticationTokens: AuthenticationTokenData(idToken: 'private-id-token'),
    );
  }

  @override
  Future<AuthenticationResults> authenticate(AuthenticateParameters params) async {
    authentications++;
    if (canceled) {
      throw const GoogleSignInException(code: GoogleSignInExceptionCode.canceled);
    }
    return const AuthenticationResults(
      user: GoogleSignInUserData(email: 'runner@example.com', id: 'runner'),
      authenticationTokens: AuthenticationTokenData(idToken: 'private-id-token'),
    );
  }

  @override
  Future<ClientAuthorizationTokenData?> clientAuthorizationTokensForScopes(
      ClientAuthorizationTokensForScopesParameters params) async {
    if (denied) {
      throw const GoogleSignInException(code: GoogleSignInExceptionCode.canceled);
    }
    if (!granted) return null;
    return const ClientAuthorizationTokenData(accessToken: 'private-access-token');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final google = FakeGoogle();
  const storage = FlutterSecureStorage();
  const key = 'trail_mania.google_drive.authorization.v1';

  TestControl newService() {
    final control = TestControl();
    DriveService(control: control).init();
    return control;
  }

  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    GoogleSignInPlatform.instance = google;
    google.canceled = false;
    google.denied = false;
    google.granted = true;
    google.lightweightError = null;
    google.authentications = 0;
    FlutterSecureStorage.setMockInitialValues({});
  });
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('first launch has no saved authorization', () async {
    expect(await newService().callNative('restore', null), {'status': 'disconnected'});
    expect(google.authentications, 0);
  });

  test('Drive consent is saved securely and restored by a new service', () async {
    final result = await newService().callNative('connect', {'server_client_id': 'web-client'});
    expect(result['status'], 'connected');
    final saved = await storage.read(key: key);
    expect(saved, contains('runner@example.com'));
    expect(saved, isNot(contains('private-access-token')));
    expect(saved, isNot(contains('private-id-token')));
    final restored = await newService().callNative('restore', null);
    expect(restored, {'status': 'connected', 'email': 'runner@example.com'});
    expect(google.authentications, 1); // Restore does not need Google or a network.
  });

  test('canceled authentication is never saved', () async {
    google.canceled = true;
    expect((await newService().callNative('connect', {'server_client_id': 'web-client'}))['status'], 'canceled');
    expect(await storage.read(key: key), isNull);
  });

  test('authentication without Drive consent is never saved', () async {
    google.denied = true;
    expect((await newService().callNative('connect', {'server_client_id': 'web-client'}))['status'], 'canceled');
    expect(await storage.read(key: key), isNull);
  });

  test('invalid saved authorization requires reconnection', () async {
    await storage.write(key: key, value: '{"email":"runner@example.com"}');
    expect(await newService().callNative('restore', null), {'status': 'disconnected'});
    expect(await storage.read(key: key), isNull);
  });

  test('new service retrieves a token from the SDK without interactive sign-in', () async {
    await newService().callNative('connect', {'server_client_id': 'web-client'});
    final result = await newService().callNative('access_token', {'server_client_id': 'web-client'});
    expect(result, {'status': 'connected', 'access_token': 'private-access-token'});
    expect(google.authentications, 1);
  });

  test('revoked Drive permission clears the saved connection', () async {
    await newService().callNative('connect', {'server_client_id': 'web-client'});
    google.granted = false;
    final service = newService();
    expect(await service.callNative('access_token', {'server_client_id': 'web-client'}),
        {'status': 'authorization_required'});
    expect(await service.callNative('restore', null), {'status': 'disconnected'});
  });

  test('temporary native sign-in failure preserves credentials for the next retry', () async {
    await newService().callNative('connect', {'server_client_id': 'web-client'});
    google.lightweightError = GoogleSignInExceptionCode.interrupted;
    final service = newService();
    expect(await service.callNative('access_token', {'server_client_id': 'web-client'}),
        {'status': 'interrupted'});
    expect(await storage.read(key: key), isNotNull);
    google.lightweightError = null;
    expect((await service.callNative('access_token', {'server_client_id': 'web-client'}))['status'],
        'connected');
  });
}
