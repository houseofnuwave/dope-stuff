/* Dope Stuff Offer Lab
 * Estimate only: marketplace fees and processing rates can change.
 * Pure arithmetic, no seller data collected or transmitted.
 * Official fee schedule checked October 2026; user can override processing assumptions.
 */
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  if (root) root.DopeOfferLab = value;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  const MAX_CENTS = 999999999;

  function dollarsToCents(value) {
    const text = String(value).trim();
    if (!/^\\d{1,7}(?:\\.\\d{1,2})?$/.test(text)) throw new Error('Enter a nonnegative amount with at most two decimals.');
    const parts = text.split('.');
    const cents = Number(parts[0]) * 100 + Number((parts[1] || '').padEnd(2, '0'));
    if (!Number.isSafeInteger(cents) || cents > MAX_CENTS) throw new Error('Amount exceeds the supported range.');
    return cents;
  }

  function percentToBasisPoints(value) {
    const text = String(value).trim();
    if (!/^\\d{1,2}(?:\\.\\d{1,2})?$|^100(?:\\.0{1,2})?$/.test(text)) {
      throw new Error('Enter a processing percentage from 0 to 100 with at most two decimals.');
    }
    const parts = text.split('.');
    return Number(parts[0]) * 100 + Number((parts[1] || '').padEnd(2, '0'));
  }

  function safeCents(value) {
    if (!Number.isSafeInteger(value) || value < 0 || value > MAX_CENTS) {
      throw new Error('Invalid monetary amount.');
    }
    return value;
  }

  function feeCents(amount, bps) {
    // Round halves up to the nearest cent, never using floating point currency.
    return Math.floor((amount * bps + 5000) / 10000);
  }

  function estimate(input) {
    const sale = safeCents(input.saleCents);
    const cost = safeCents(input.costCents);
    const postage = safeCents(input.postageCents);
    const buyerShipping = safeCents(input.buyerShippingCents);
    const fixedProcessing = safeCents(input.processingFixedCents);
    const bps = percentToBasisPoints(input.processingPercent);
    const mode = input.shippingMode;
    if (mode !== 'grailed_label' && mode !== 'own_label') throw new Error('Choose a supported shipping mode.');
    if (mode === 'grailed_label' && buyerShipping !== 0) {
      throw new Error('Buyer shipping must be zero for this Grailed-label estimate.');
    }
    if (sale <= 0) throw new Error('Enter the offer amount you are considering.');

    // Grailed's commission base includes buyer-paid shipping ONLY for own labels.
    const commissionBase = sale + (mode === 'own_label' ? buyerShipping : 0);
    const commissionBps = commissionBase < 12000 ? 600 : 900;
    const commission = commissionBps === 600
      ? Math.max(199, feeCents(commissionBase, commissionBps))
      : feeCents(commissionBase, commissionBps);
    // Processing base is an estimate; settlement may differ due to taxes or provider details.
    const processingBase = commissionBase;
    const processing = feeCents(processingBase, bps) + fixedProcessing;
    const receipts = commissionBase;
    const payout = receipts - commission - processing - postage;
    const profit = payout - cost;

    return Object.freeze({
      commissionBaseCents: commissionBase,
      commissionRatePercent: commissionBps / 100,
      commissionCents: commission,
      processingCents: processing,
      grossReceiptsCents: receipts,
      postageCents: postage,
      sellerPayoutCents: payout,
      costCents: cost,
      netProfitCents: profit,
      marginPercent: receipts ? Math.round((profit / receipts) * 1000) / 10 : null,
      returnOnCostPercent: cost ? Math.round((profit / cost) * 1000) / 10 : null,
      isLoss: profit < 0
    });
  }

  return Object.freeze({ dollarsToCents, percentToBasisPoints, feeCents, estimate });
});
