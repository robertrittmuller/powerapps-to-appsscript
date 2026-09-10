// HtmlService's async, immutable google.script.run builder contract.
(function () {
  const pending = new Set();
  window.__waitForGasIdle = async function () {
    do {
      await Promise.allSettled([...pending]);
      // Cross a task boundary after callbacks and their Promise chains. Unlike
      // timers, MessageChannel also works while the test clock is paused.
      await new Promise(resolve => {
        const channel = new MessageChannel();
        channel.port1.onmessage = () => {channel.port1.close(); channel.port2.close(); resolve();};
        channel.port2.postMessage(null);
      });
    } while (pending.size);
    return true;
  };
  function assertTransport(value, ancestors = []) {
    if (value == null || ['string', 'number', 'boolean'].includes(typeof value)) return;
    if (typeof value !== 'object' || value instanceof Date || value.nodeType || ancestors.includes(value))
      throw new Error('google.script.run cannot transport this value');
    Object.values(value).forEach(child => assertTransport(child, [...ancestors, value]));
  }
  function runner(success, failure) {
    return new Proxy({}, {get(_target, name) {
      if (name === 'withSuccessHandler') return fn => runner(fn, failure);
      if (name === 'withFailureHandler') return fn => runner(success, fn);
      return (...args) => {
        assertTransport(args);
        const request = window.__gasCall({fn: name, args}).then(result => {
        if (result.error) { if (failure) failure({message: result.error}); }
        else if (success) success(result.result);
        }).catch(error => { if (failure) failure({message: String(error)}); });
        pending.add(request);
        request.then(()=>pending.delete(request),()=>pending.delete(request));
        return request;
      };
    }});
  }
  window.google = {script: {run: runner()}};
})();
