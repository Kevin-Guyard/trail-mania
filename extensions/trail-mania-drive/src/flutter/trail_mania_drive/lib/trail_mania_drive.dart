import 'dart:convert';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_sign_in/google_sign_in.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) =>
      control.type == 'TrailManiaDrive' ? DriveService(control: control) : null;
}

class DriveService extends FletService {
  DriveService({required super.control});

  static const _key = 'trail_mania.google_drive.authorization.v1';
  static const _scopes = ['https://www.googleapis.com/auth/drive.appdata'];
  static const _storage = FlutterSecureStorage();
  // The Google SDK owns the persistent Google session and refresh mechanism.
  // Passwords and refresh tokens are never sent to Python or bundled in APKs.
  static Future<void>? _initialization;
  GoogleSignInAccount? _account;

  bool get _supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invoke);
  }

  Future<void> _initialize(String clientId) async {
    if (clientId.isEmpty) throw StateError('missing_configuration');
    _initialization ??= GoogleSignIn.instance.initialize(serverClientId: clientId);
    try {
      await _initialization;
    } catch (_) {
      _initialization = null;
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _restore() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return {'status': 'disconnected'};
    try {
      final saved = jsonDecode(raw) as Map<String, dynamic>;
      if (saved['scope'] != _scopes.single || saved['email'] is! String ||
          saved['account_id'] is! String || saved['client_id'] is! String) {
        throw const FormatException();
      }
      return {'status': 'connected', 'email': saved['email']};
    } on FormatException {
      await _storage.delete(key: _key);
      return {'status': 'disconnected'};
    } on TypeError {
      await _storage.delete(key: _key);
      return {'status': 'disconnected'};
    }
  }

  Future<Map<String, dynamic>> _invoke(String name, dynamic args) async {
    if (!_supported) return {'status': 'unsupported'};
    try {
      if (name == 'restore') return await _restore();
      final clientId = args?['server_client_id'] as String? ?? '';
      await _initialize(clientId);
      if (name == 'connect') {
        final account = await GoogleSignIn.instance.authenticate(scopeHint: _scopes);
        // Authentication alone does not authorize Drive: both must succeed.
        final authorization =
            await account.authorizationClient.authorizeScopes(_scopes);
        if (authorization.accessToken.isEmpty) {
          return {'status': 'authorization_required'};
        }
        await _storage.write(key: _key, value: jsonEncode({
          'account_id': account.id,
          'email': account.email,
          'client_id': clientId,
          'scope': _scopes.single,
        }));
        _account = account;
        return {'status': 'connected', 'email': account.email};
      }
      if (name == 'access_token') {
        final raw = await _storage.read(key: _key);
        if (raw == null) return {'status': 'authorization_required'};
        final saved = jsonDecode(raw) as Map<String, dynamic>;
        // Preserve temporary failures (e.g. a paused app) instead of interpreting
        // a suppressed exception as a signed-out account and deleting its state.
        _account ??= await GoogleSignIn.instance.attemptLightweightAuthentication(
          reportAllExceptions: true,
        );
        if (_account == null || _account!.id != saved['account_id'] ||
            saved['client_id'] != clientId) {
          await _storage.delete(key: _key);
          return {'status': 'authorization_required'};
        }
        final authorization =
            await _account!.authorizationClient.authorizationForScopes(_scopes);
        if (authorization == null) {
          await _storage.delete(key: _key);
          return {'status': 'authorization_required'};
        }
        return {'status': 'connected', 'access_token': authorization.accessToken};
      }
      return {'status': 'error'};
    } on GoogleSignInException catch (error) {
      // Return only a stable code; raw exceptions may include sensitive details.
      return {'status': error.code.name};
    } catch (_) {
      return {'status': 'error'};
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invoke);
    super.dispose();
  }
}
