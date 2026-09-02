type JsonCredential = Record<string, unknown>;

function b64urlToBytes(value: string): Uint8Array {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  const binary = window.atob(base64);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function bytesToB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function toCreationOptions(
  publicKey: Record<string, unknown>,
): PublicKeyCredentialCreationOptions {
  const options = { ...publicKey } as Record<string, unknown>;
  options.challenge = b64urlToBytes(String(options.challenge));
  const user = options.user as Record<string, unknown> | undefined;
  if (user?.id) {
    options.user = { ...user, id: b64urlToBytes(String(user.id)) };
  }
  const exclude = options.excludeCredentials as Array<Record<string, unknown>> | undefined;
  if (exclude) {
    options.excludeCredentials = exclude.map((credential) => ({
      ...credential,
      id: b64urlToBytes(String(credential.id)),
    }));
  }
  return options as unknown as PublicKeyCredentialCreationOptions;
}

export function toRequestOptions(
  publicKey: Record<string, unknown>,
): PublicKeyCredentialRequestOptions {
  const options = { ...publicKey } as Record<string, unknown>;
  options.challenge = b64urlToBytes(String(options.challenge));
  const allow = options.allowCredentials as Array<Record<string, unknown>> | undefined;
  if (allow) {
    options.allowCredentials = allow.map((credential) => ({
      ...credential,
      id: b64urlToBytes(String(credential.id)),
    }));
  }
  return options as unknown as PublicKeyCredentialRequestOptions;
}

export function credentialToJSON(credential: Credential): JsonCredential {
  const maybeJson = credential as Credential & { toJSON?: () => JsonCredential };
  if (maybeJson.toJSON) return maybeJson.toJSON();
  const publicKey = credential as PublicKeyCredential;
  const response = publicKey.response as AuthenticatorAttestationResponse &
    AuthenticatorAssertionResponse;
  const json: JsonCredential = {
    id: publicKey.id,
    type: publicKey.type,
    rawId: bytesToB64url(publicKey.rawId),
    response: {},
  };
  const responseJson = json.response as JsonCredential;
  if (response.clientDataJSON) {
    responseJson.clientDataJSON = bytesToB64url(response.clientDataJSON);
  }
  if ("attestationObject" in response && response.attestationObject) {
    responseJson.attestationObject = bytesToB64url(response.attestationObject);
  }
  if ("authenticatorData" in response && response.authenticatorData) {
    responseJson.authenticatorData = bytesToB64url(response.authenticatorData);
  }
  if ("signature" in response && response.signature) {
    responseJson.signature = bytesToB64url(response.signature);
  }
  if ("userHandle" in response && response.userHandle) {
    responseJson.userHandle = bytesToB64url(response.userHandle);
  }
  return json;
}
