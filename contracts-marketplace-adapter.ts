/** Future-only interface. This repo does NOT implement marketplace automation. */
export type MarketplaceCapabilities = {
  publish: boolean;
  update: boolean;
  remove: boolean;
  readOrders: boolean;
  receiveWebhooks: boolean;
};
export type IntegrationState =
  | { kind: 'manual'; explanation: string }
  | { kind: 'unavailable'; explanation: string }
  | { kind: 'pending_partner_approval'; explanation: string }
  | { kind: 'connected'; providerAccountId: string; verifiedAt: string };
export type RemoteResult =
  | { ok: true; providerListingId: string; verifiedAt: string }
  | { ok: false; code: 'NOT_AUTHORIZED' | 'VALIDATION' | 'RATE_LIMIT' | 'RETRYABLE' | 'UNKNOWN'; retryAfterSeconds?: number };
export interface AuthorizedMarketplaceAdapter {
  readonly channelId: string;
  readonly capabilities: MarketplaceCapabilities;
  readonly integrationState: IntegrationState;
  /** Must have prior formal authorization; use server-side encrypted OAuth only. */
  publish?(ownerId: string, sku: string, idempotencyKey: string): Promise<RemoteResult>;
  remove?(ownerId: string, providerListingId: string, idempotencyKey: string): Promise<RemoteResult>;
}
