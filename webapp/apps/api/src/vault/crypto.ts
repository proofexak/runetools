/**
 * Vault crypto: a 256-bit key derived from the master password with argon2id, and
 * AES-256-GCM per record (random 96-bit nonce, 128-bit tag appended to the ciphertext).
 * The AAD binds a record to its row, so a ciphertext copied onto another account fails.
 */
import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { hashRaw } from "@node-rs/argon2";

export interface KdfParams { memoryCost: number; timeCost: number; parallelism: number }

/** 64 MiB, 3 passes: ~0.2–0.5 s per unlock, which is the point. */
export const DEFAULT_KDF: KdfParams = { memoryCost: 64 * 1024, timeCost: 3, parallelism: 1 };

const TAG = 16;

export function newSalt(): Buffer {
  return randomBytes(16);
}

export async function deriveKey(master: string, salt: Buffer, kdf: KdfParams): Promise<Buffer> {
  // algorithm 2 = Argon2id (the package's const enum can't be imported under isolatedModules)
  return hashRaw(master, { ...kdf, salt, outputLen: 32, algorithm: 2 });
}

export function seal(key: Buffer, plaintext: string, aad: string): { ciphertext: Buffer; nonce: Buffer } {
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  cipher.setAAD(Buffer.from(aad, "utf8"));
  const body = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  return { ciphertext: Buffer.concat([body, cipher.getAuthTag()]), nonce };
}

/** Throws if the key is wrong or the record was tampered with / moved. */
export function open(key: Buffer, ciphertext: Buffer, nonce: Buffer, aad: string): string {
  const decipher = createDecipheriv("aes-256-gcm", key, nonce);
  decipher.setAAD(Buffer.from(aad, "utf8"));
  decipher.setAuthTag(ciphertext.subarray(ciphertext.length - TAG));
  return Buffer.concat([decipher.update(ciphertext.subarray(0, ciphertext.length - TAG)), decipher.final()]).toString("utf8");
}

export const CHECK_PLAINTEXT = "runetools-vault-check";
export const CHECK_AAD = "vault-check";
export const recordAad = (accountId: number) => `credential:${accountId}`;
