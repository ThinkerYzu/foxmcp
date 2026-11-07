(async function runConsentChecks(source) {
  const checks = [];
  const check = (value, label) => { if (!value) throw Error(label); checks.push(label); };
  const settle = async () => { for (let i = 0; i < 60; i++) await Promise.resolve(); };
  const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
  async function app(enabled = true, popupFails = false, delayedFocus = false) {
    let now = 100000, sequence = 0, focused = 1;
    const timers = new Map(), executions = [], switches = [], updates = [], removed = [], popups = [];
    const tabs = new Map([1, 2, 3].map(id => [id, {id, title: `Tab ${id}`, url: 'https://example.org/page', status:'complete', windowId: id === 3 ? 2 : 1, active: id === 1}]));
    const socket = {readyState: 1, send() {}};
    let failExecute = null, popupFailures = 0, popupWait = null;
    const popupViews = [], focusListeners = [], activationListeners = [];
    const browser = {
      extension: {getViews: () => popupViews},
      tabs: {
        onActivated: {addListener: f => activationListeners.push(f)},
        onUpdated: {addListener: f => updates.push(f)}, onRemoved: {addListener: f => removed.push(f)},
        async get(id) { if (!tabs.has(id)) throw Error('Tab closed'); return {...tabs.get(id)}; },
        async update(id, patch) {
          const tab = tabs.get(id); if (!tab) throw Error('Tab closed');
          if (patch.active) for (const t of tabs.values()) if (t.windowId === tab.windowId) t.active = false;
          Object.assign(tab, patch); switches.push(id); return {...tab};
        },
        async executeScript(id, options) {
          executions.push({id, ...options});
          if (failExecute) return await failExecute;
          return [42];
        }
      },
      windows: {onFocusChanged: {addListener: f => focusListeners.push(f)}, async update(id) { if (!delayedFocus) focused = id; }, async get(id) { return {focused: id === focused}; }},
      browserAction: {async openPopup() { popups.push(now); if (popupWait) await popupWait; if (popupFails) throw Error('User gesture required'); if (popupFailures-- > 0) throw Error('Another popup is open'); }, async setBadgeText() {}}
    };
    class FakeDate extends Date { static now() { return now; } }
    const api = await new AsyncFunction('browser', 'Date', 'setTimeout', 'clearTimeout', `
      const requestSockets = new Map(); const websocket = arguments[4]; const WebSocket = {OPEN:1};
      ${source}
      return {gate:scriptConsent, requestSockets};
    `)(browser, FakeDate, (f,ms) => { const id=++sequence;timers.set(id,{f,due:now+ms});return id; }, id=>timers.delete(id), socket);
    api.gate.configure(enabled);
    async function tick(ms) {
      const end = now + ms;
      while (true) {
        const next = [...timers].filter(([,t])=>t.due<=end).sort((a,b)=>a[1].due-b[1].due)[0];
        if (!next) break;
        now=next[1].due;timers.delete(next[0]);next[1].f();await settle();
      }
      now=end;await settle();
    }
    function run(id, tabId=1, script='40+2') {
      api.requestSockets.set(id,socket);
      return api.gate.run(id,tabId,script).then(value=>({value}), error=>({error:error.code || error.message}));
    }
    async function decide(allowed) { const view=await api.gate.view(); return api.gate.decide(view.token,allowed); }
    function navigate(id,url,status='complete') { Object.assign(tabs.get(id),{url,status});for (const callback of updates) callback(id,{url,status},{...tabs.get(id)}); }
    return {...api,browser,tabs,executions,switches,tick,run,decide,navigate,popupViews,popups,
      failPopups(count) { popupFailures=count; }, holdPopup(promise) {popupWait=promise;},
      close(id) { tabs.delete(id);for (const callback of removed) callback(id); },
      holdExecution(promise) {failExecute=promise;},
      focus(id, notify=true) {focused=id;if(notify)for(const callback of focusListeners)callback(id);},
      activate(id) { for(const tab of tabs.values())if(tab.windowId===tabs.get(id).windowId)tab.active=tab.id===id;for(const callback of activationListeners)callback({tabId:id,windowId:tabs.get(id).windowId}); }};
  }
  function popup(app) {
    let unload;
    const view = {closed:false, closing:false,
      addEventListener(type, callback) { if (type === 'unload') unload = callback; },
      removeEventListener() { unload = null; },
      close() { this.closing = true; }};
    app.popupViews.push(view);
    return {view, finish() { view.closed = true; app.popupViews.splice(app.popupViews.indexOf(view),1); unload(); }};
  }
  const closing=await app();
  const closingPopup=popup(closing);
  const pending=closing.run('close-first'), queued=closing.run('close-next',3);
  await settle();
  const approval=closing.decide(true);await settle();
  check(await approval && !closingPopup.view.closed, 'Allow is acknowledged while popup unload is still pending');
  closingPopup.view.close();
  check(closing.executions.length===0 && closing.switches.join(',')==='1', 'injection and next-tab activation wait for popup unload');
  closingPopup.finish();await approval;await settle();
  check((await pending).value[0]===42 && closing.switches.join(',')==='1,3', 'popup unload releases script and next prompt');
  const denyPopup=popup(closing);
  const denial=closing.decide(false);await settle();denyPopup.view.close();
  check(denyPopup.view.closing && closing.gate.current.tabId===3, 'Deny also waits for popup closure');
  denyPopup.finish();await denial;
  check((await queued).error==='SCRIPT_DENIED', 'closed Deny prompt rejects without executing');

  const stale=await app();const stalePopup=popup(stale);
  const staleJob=stale.run('stale-close');await settle();
  await stale.decide(true);await settle();
  stale.navigate(1,'https://example.org:8443/');stalePopup.finish();
  check((await staleJob).error==='SCRIPT_TARGET_CHANGED' && stale.executions.length===0,
    'origin change during popup closure cannot authorize stale injection');

  const expiry=await app();const expiryPopup=popup(expiry);
  const expiryJob=expiry.run('expired-close');await settle();
  await expiry.decide(true);await settle();
  await expiry.tick(60000);expiryPopup.finish();
  check((await expiryJob).error==='SCRIPT_CONSENT_TIMEOUT' && expiry.executions.length===0,
    'deadline during popup closure cannot authorize expired injection');

  const history=await app();
  const historyJob=history.run('history');await settle();
  const historyView=await history.gate.view();const initialPopups=history.popups.length;
  history.navigate(1,'https://example.org/previous','loading');await settle();
  check(history.popups.length===initialPopups, 'history navigation waits until target finishes loading');
  history.navigate(1,'https://example.org/previous');await settle();
  check(history.popups.length===initialPopups+1, 'Back navigation re-presents the pending same-origin prompt');
  history.navigate(1,'https://example.org/next');await settle();
  check(history.popups.length===initialPopups+2, 'Forward or same-document navigation re-presents the prompt');
  const afterHistory=await history.gate.view();
  check(afterHistory.token===historyView.token && afterHistory.deadline===historyView.deadline && history.executions.length===0,
    'history reopening keeps the original token, deadline and unapproved state');
  history.focus(2);history.navigate(1,'https://example.org/hidden');await settle();
  check(history.popups.length===initialPopups+2, 'navigation never opens a popup over a different focused window');
  history.focus(1);await history.decide(false);await historyJob;

  const transient=await app();transient.failPopups(1);
  const transientJob=transient.run('transient');await settle();
  check(transient.popups.length===1 && transient.executions.length===0, 'popup opening failure leaves consent pending');
  await transient.tick(200);
  check(transient.popups.length===2, 'transient popup conflict is retried');
  await transient.decide(false);await transientJob;

  const abandoned=await app();abandoned.failPopups(10);
  const abandonedJob=abandoned.run('abandoned');await settle();
  abandoned.navigate(1,'https://example.org:8443/');await abandonedJob;
  await abandoned.tick(1000);
  check(abandoned.popups.length===1 && !abandoned.gate.current, 'origin invalidation cancels pending popup retry');

  const restricted=await app(true,true);const restrictedJob=restricted.run('restricted');await settle();
  await restricted.tick(1000);
  check(restricted.popups.length===1, 'user-gesture restriction uses manual fallback without retrying');
  await restricted.decide(false);await restrictedJob;

  const deciding=await app();const decidingPopup=popup(deciding);
  const decidingJob=deciding.run('deciding');await settle();const beforeDecision=deciding.popups.length;
  await deciding.decide(true);deciding.navigate(1,'https://example.org/while-closing');await settle();
  check(deciding.popups.length===beforeDecision, 'navigation cannot reopen a popup after its decision was accepted');
  decidingPopup.finish();await decidingJob;

  const bounded=await app();bounded.failPopups(Infinity);
  const boundedJob=bounded.run('bounded');await settle();await bounded.tick(2000);
  check(bounded.popups.length===6 && bounded.executions.length===0, 'popup retries stop after the bounded budget');
  await bounded.decide(false);await boundedJob;

  const resolved=await app();resolved.failPopups(1);
  const resolvedJob=resolved.run('resolved');await settle();
  await resolved.decide(false);await resolvedJob;await resolved.tick(1000);
  check(resolved.popups.length===1, 'accepted decision clears a queued popup retry');

  const serialized=await app();let releasePopup;
  serialized.holdPopup(new Promise(resolve=>{releasePopup=resolve;}));
  const serializedJob=serialized.run('serialized');await settle();
  serialized.navigate(1,'https://example.org/back');serialized.navigate(1,'https://example.org/forward');await settle();
  check(serialized.popups.length===1, 'overlapping history events cannot open concurrent popups');
  serialized.holdPopup(null);releasePopup();await settle();await serialized.tick(200);
  check(serialized.popups.length===2, 'overlapping navigation coalesces to one follow-up presentation');
  await serialized.decide(false);await serializedJob;

  const delayed=await app(true,false,true);
  const delayedJob=delayed.run('delayed-focus',3);await settle();
  const delayedDeadline=delayed.gate.current.deadline;
  const delayedDiagnostic=await delayed.gate.diagnostics();
  check(delayedDiagnostic.pending && delayedDiagnostic.waitingForVisibility && !delayedDiagnostic.visible,
    'read-only diagnostics distinguish pending visibility from popup rejection');
  check(delayed.popups.length===0 && delayed.executions.length===0, 'delayed native focus keeps approval pending');
  delayed.focus(2,false);await delayed.tick(200);
  check(delayed.popups.length===1, 'visibility retry opens after delayed focus without another navigation');
  check(delayed.gate.current.deadline===delayedDeadline, 'focus recovery does not extend the decision deadline');
  await delayed.decide(false);await delayedJob;
  check(!(await delayed.gate.diagnostics()).pending, 'diagnostics clear pending state after rejection');

  const lateFocus=await app(true,false,true);
  const lateJob=lateFocus.run('late-focus',3);await settle();await lateFocus.tick(2000);
  check(lateFocus.popups.length===0, 'unfocused target is never covered by a popup');
  lateFocus.focus(2);await settle();
  check(lateFocus.popups.length===1, 'window-focus event resumes deferred presentation after retry budget');
  const opened=lateFocus.popups.length;lateFocus.focus(2);await settle();
  check(lateFocus.popups.length===opened, 'focus after successful opening does not reopen an ordinarily dismissed popup');
  await lateFocus.decide(false);await lateJob;

  const inactive=await app();const inactiveJob=inactive.run('inactive');await settle();
  inactive.tabs.get(1).active=false;inactive.navigate(1,'https://example.org/back');await settle();
  const beforeActivation=inactive.popups.length;
  inactive.activate(1);await settle();
  check(inactive.popups.length===beforeActivation+1, 'target-tab activation resumes a prompt deferred during history navigation');
  await inactive.decide(false);await inactiveJob;

  const directives=await app();
  for (const script of ['"use strict"; x=1', '// comment\n"use strict"\nx=1',
    '"another directive"; /*comment*/ "use strict"; x=1']) {
    check(directives.gate.hasStrictDirective(script), 'recognizes strict directive: '+script);
  }
  for (const script of ['"use strict" + "value"', '"use strict"\n[0]', '"not strict"; 42']) {
    check(!directives.gate.hasStrictDirective(script), 'does not invent strict mode: '+script);
  }
  const off=await app(false);
  check((await off.run('off')).value[0]===42 && !off.gate.current, 'default-off executes without approval');
  check(off.switches.length===0, 'disabled gate preserves background focus');

  const offNavigation=await app(false);
  const getTab=offNavigation.browser.tabs.get;
  let reads=0;
  offNavigation.browser.tabs.get=async id=>{
    const tab=await getTab(id);
    if (++reads===2) offNavigation.navigate(id,'https://example.org:8443/');
    return tab;
  };
  const navigated=await offNavigation.run('off-navigation');
  check(navigated.value?.[0]===42 && offNavigation.executions.length===1,
    'disabled gate does not cancel execution on an origin-change event');
  check(offNavigation.executions[0].code==='40+2' && offNavigation.switches.length===0,
    'disabled navigation retains the original code and background focus');

  const a=await app();
  const first=a.run('first',2), same=a.run('same',2), third=a.run('third',3);
  await settle();
  check(a.executions.length===0 && a.switches.join(',')==='2', 'queued tabs never interrupt first prompt');
  check(a.gate.current.jobs.size===2, 'concurrent same-tab attempts share a prompt');
  const view=await a.gate.view();
  check(view.origin==='https://example.org' && view.visible && view.deadline===160000, 'approval identifies visible origin with full minute');
  await a.decide(true);await settle();
  check((await first).value[0]===42 && (await same).value[0]===42, 'approval releases concurrent injections');
  check(a.switches.join(',')==='2,3' && a.gate.current.tabId===3, 'next tab activates after first decision');
  check((await a.gate.view()).visible, 'target in another window is focused');
  await a.decide(false);check((await third).error==='SCRIPT_DENIED','explicit denial rejects');
  check((await a.run('denied',3)).error==='SCRIPT_DENIED' && !a.gate.current,'denial remembered without reprompt');
  const count=a.switches.length;await a.run('allowed',2);
  check(a.switches.length===count, 'approved tab executes in background without switching');
  check(a.executions[0].code.includes('this.location.origin !== "https://example.org"'), 'actual injection guards destination origin');
  const code = a.executions.at(-1).code;
  const evaluate = new Function('code', 'return eval(code)');
  check(evaluate.call({location:{origin:'https://example.org'}}, code) === 42, 'guard preserves script completion value');
  let wrongOrigin = false;
  try { evaluate.call({location:{origin:'https://other.example.org'}}, code); } catch (_) { wrongOrigin = true; }
  check(wrongOrigin, 'injected guard rejects the actual wrong origin');
  await a.run('strict',2,'"use strict"; foxmcpStrictLeak=1');
  let strictError = false;
  try { evaluate.call({location:{origin:'https://example.org'}}, a.executions.at(-1).code); }
  catch (error) { strictError = error instanceof ReferenceError; }
  check(strictError && typeof globalThis.foxmcpStrictLeak === 'undefined', 'origin guard preserves strict-mode semantics');
  a.navigate(2,'https://example.org/reload');await a.run('reload',2);
  check(!a.gate.current,'same-origin navigation retains grant');
  a.navigate(2,'https://other.example.org/');
  const changed=a.run('changed',2);await settle();
  check(a.gate.current.origin==='https://other.example.org','origin change requires approval');
  a.navigate(2,'https://example.org/back');
  check((await changed).error==='SCRIPT_TARGET_CHANGED','navigation cancels pending injection');
  check(!a.gate.decisions.has(2),'returning to earlier origin does not revive approval');
  const closed=a.run('closed',2);await settle();a.close(2);
  check((await closed).error==='SCRIPT_TARGET_CHANGED','tab closure cancels approval');

  const timeout=await app(true,true);
  const expired=timeout.run('expire');await settle();
  const oldToken=timeout.gate.current.token;
  await timeout.tick(59999);check(timeout.executions.length===0 && !!timeout.gate.current,'older-version fallback still waits for consent');
  await timeout.tick(1);check((await expired).error==='SCRIPT_CONSENT_TIMEOUT','60-second deadline rejects without execution');
  check(!timeout.gate.decisions.size,'timeout does not remember Deny');
  let late=false;try {await timeout.gate.decide(oldToken,true);}catch(_){late=true;}
  check(late && !timeout.executions.length,'late approval cannot execute expired work');
  const retry=timeout.run('retry');await settle();check(!!timeout.gate.current,'timeout permits a fresh approval attempt');
  timeout.gate.disconnected();check((await retry).error==='SCRIPT_CONSENT_CANCELLED','disconnect cancels pending approval');

  const switching=await app();
  const existing=switching.run('existing'), batch=switching.run('batch',2);await settle();
  switching.gate.configure(false);
  const later=switching.run('later',3);await settle();
  check(switching.gate.enabled && switching.gate.transition===false,'toggle waits for pending batch');
  await switching.decide(true);await existing;await settle();
  check(switching.gate.current.tabId===2 && !switching.executions.some(e=>e.id===3),'later arrival waits behind policy transition');
  await switching.decide(false);await batch;await later;
  check(!switching.gate.enabled && switching.gate.decisions.size===0,'drained batch applies toggle and clears decisions');
  check(switching.switches.join(',')==='1,2','later disabled request does not steal focus');
  switching.gate.configure(true);
  const fresh=switching.run('fresh');await settle();
  check(!!switching.gate.current,'re-enabling starts with fresh decisions');
  switching.gate.cancel('fresh');await fresh;

  const executing=await app(false);let finish;
  executing.holdExecution(new Promise(resolve=>{finish=resolve;}));
  const running=executing.run('running');await settle();executing.gate.configure(true);
  check(!executing.gate.enabled && executing.gate.transition===true,'toggle also waits for executing injections');
  executing.gate.cancel('running');
  check(!executing.gate.enabled && executing.gate.jobs.has('running'), 'cancellation cannot let toggle overtake running JavaScript');
  finish([1]);await running;check(executing.gate.enabled,'toggle applies when execution completes');

  const hidden=await app();const waiting=hidden.run('hidden');await settle();
  const token=(await hidden.gate.view()).token;hidden.focus(2);
  let refused=false;try{await hidden.gate.decide(token,true);}catch(_){refused=true;}
  check(refused && !hidden.executions.length,'approval refused when target window loses focus');
  hidden.gate.cancel('hidden');await waiting;
  const restarted=await app();check(!restarted.gate.decisions.size,'new extension instance forgets decisions');
  return checks;
})
