// HtmlService's async, immutable google.script.run builder contract.
(function () {
  function runner(success, failure) {
    return new Proxy({}, {get(_target, name) {
      if (name === 'withSuccessHandler') return fn => runner(fn, failure);
      if (name === 'withFailureHandler') return fn => runner(success, fn);
      return (...args) => window.__gasCall({fn: name, args}).then(result => {
        if (result.error) { if (failure) failure({message: result.error}); }
        else if (success) success(result.result);
      }).catch(error => { if (failure) failure({message: String(error)}); });
    }});
  }
  window.google = {script: {run: runner()}};
})();
