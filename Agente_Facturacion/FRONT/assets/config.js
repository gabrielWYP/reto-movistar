window.SONIA_BILLING_UI = Object.freeze({
  apiBase: window.location.pathname.startsWith("/agents/billing") ? "/api/billing" : "/api",
  demo: Object.freeze({
    customer: "CLIENT_00434",
    account: "993722637",
    arithmeticInvoice: "S300-0256413",
    missingCurrencyInvoice: "FOBF-00121753",
    zeroInvoice: "S7AA-0067926518",
    creditInvoice: "S1AA-0052649961"
  })
});
