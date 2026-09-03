(() => {
  const i18n = window.shopAlertI18n || {};
  const languageSelects = [...document.querySelectorAll('[data-language-select]')];
  const themeSelects = [...document.querySelectorAll('[data-theme-select]')];
  const preferenceTriggers = [...document.querySelectorAll('[data-preference-trigger]')];
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  const appearanceThemes = ['system', 'light', 'dark'];
  const colorThemes = ['coral', 'yellow', 'purple'];
  const preservedScrollKey = 'shopalert-preserved-scroll';
  const setScrollPositionInstantly = (position) => {
    const previousBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = 'auto';
    window.scrollTo(0, position);
    document.documentElement.style.scrollBehavior = previousBehavior;
  };
  const preserveScrollForms = [...document.querySelectorAll('[data-preserve-scroll]')];
  // Identified by action plus position among the forms posting to that action,
  // so another form appearing or disappearing cannot shift the match.
  const preserveScrollAnchorKey = (form) => {
    const action = form.getAttribute('action') || window.location.pathname;
    const sameAction = preserveScrollForms.filter(
      (item) => (item.getAttribute('action') || window.location.pathname) === action,
    );
    return `${action}#${sameAction.indexOf(form)}`;
  };
  // A translated page is not the same height, so the pixel offset alone would
  // drop the visitor somewhere else. The form they submitted is recorded as an
  // anchor and put back at the same place in the viewport.
  const saveScrollPosition = (anchor) => {
    const anchored = preserveScrollForms.includes(anchor);
    try {
      sessionStorage.setItem(preservedScrollKey, JSON.stringify({
        path: window.location.pathname,
        position: window.scrollY,
        anchorKey: anchored ? preserveScrollAnchorKey(anchor) : '',
        anchorTop: anchored ? Math.round(anchor.getBoundingClientRect().top) : null,
        savedAt: Date.now(),
      }));
    } catch (_error) {}
  };
  const readTheme = () => {
    try { return localStorage.getItem('shopalert-theme') || 'light'; }
    catch (_error) { return 'light'; }
  };
  const readColorTheme = () => {
    try { return localStorage.getItem('shopalert-color-theme') || 'coral'; }
    catch (_error) { return 'coral'; }
  };
  const applyTheme = (preference) => {
    const dark = preference === 'dark' || (preference === 'system' && systemTheme.matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.documentElement.dataset.themePreference = preference;
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  };
  // One select carries both halves of the theme, grouped by color, so the value
  // travels as "<color>:<appearance>".
  const themeSelectValue = (color, appearance) => `${color}:${appearance}`;
  const savedTheme = appearanceThemes.includes(readTheme()) ? readTheme() : 'light';
  const savedColorTheme = colorThemes.includes(readColorTheme()) ? readColorTheme() : 'coral';
  languageSelects.forEach((select) => { select.value = document.documentElement.lang; });
  themeSelects.forEach((select) => { select.value = themeSelectValue(savedColorTheme, savedTheme); });

  languageSelects.forEach((select) => {
    select.addEventListener('change', () => {
      const locale = ['en-US', 'zh-TW'].includes(select.value) ? select.value : 'en-US';
      languageSelects.forEach((item) => { item.value = locale; });
      const preferenceLocale = select.form.querySelector('[data-preference-locale]');
      if (preferenceLocale && locale !== document.documentElement.lang) {
        preferenceLocale.value = locale;
        if (typeof preferenceLocale.form.requestSubmit === 'function') {
          preferenceLocale.form.requestSubmit();
        } else {
          saveScrollPosition(preferenceLocale.form);
          preferenceLocale.form.submit();
        }
      }
    });
  });
  themeSelects.forEach((select) => {
    select.addEventListener('change', () => {
      const [selectedColor, selectedAppearance] = select.value.split(':');
      const color = colorThemes.includes(selectedColor) ? selectedColor : 'coral';
      const appearance = appearanceThemes.includes(selectedAppearance) ? selectedAppearance : 'light';
      try { localStorage.setItem('shopalert-theme', appearance); } catch (_error) {}
      try { localStorage.setItem('shopalert-color-theme', color); } catch (_error) {}
      applyTheme(appearance);
      document.documentElement.dataset.colorTheme = color;
      themeSelects.forEach((item) => { item.value = themeSelectValue(color, appearance); });
    });
  });
  systemTheme.addEventListener('change', () => {
    if (readTheme() === 'system') applyTheme('system');
  });
  applyTheme(savedTheme);
  document.documentElement.dataset.colorTheme = savedColorTheme;

  // The footer selector is a popover, so the panel only exists on screen while
  // its trigger is open.
  const preferenceSelectorOf = (trigger) => trigger.closest('[data-preference-menu]');
  const setPreferenceOpen = (selector, open) => {
    if (!selector) return;
    selector.dataset.open = open ? 'true' : 'false';
    const trigger = selector.querySelector('[data-preference-trigger]');
    if (trigger) trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  preferenceTriggers.forEach((trigger) => {
    const selector = preferenceSelectorOf(trigger);
    setPreferenceOpen(selector, false);
    trigger.addEventListener('click', () => {
      const open = selector.dataset.open !== 'true';
      preferenceTriggers.forEach((item) => setPreferenceOpen(preferenceSelectorOf(item), false));
      setPreferenceOpen(selector, open);
    });
  });
  if (preferenceTriggers.length) {
    document.addEventListener('click', (event) => {
      preferenceTriggers.forEach((trigger) => {
        const selector = preferenceSelectorOf(trigger);
        if (selector && selector.dataset.open === 'true' && !selector.contains(event.target)) {
          setPreferenceOpen(selector, false);
        }
      });
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      preferenceTriggers.forEach((trigger) => {
        const selector = preferenceSelectorOf(trigger);
        if (selector && selector.dataset.open === 'true') {
          setPreferenceOpen(selector, false);
          trigger.focus();
        }
      });
    });
  }

  preserveScrollForms.forEach((form) => {
    form.addEventListener('submit', () => saveScrollPosition(form));
  });

  const passwordChangeForm = document.querySelector('[data-password-change-form]');
  if (passwordChangeForm) {
    const newPasswordInput = passwordChangeForm.querySelector('[name="new_password"]');
    const confirmPasswordInput = passwordChangeForm.querySelector('[name="confirm_password"]');
    const newPasswordCheck = passwordChangeForm.querySelector('[data-new-password-check]');
    const confirmPasswordCheck = passwordChangeForm.querySelector('[data-confirm-password-check]');
    const visibilityButtons = [...passwordChangeForm.querySelectorAll('[data-password-visibility-toggle]')];
    const setPasswordCheck = (element, state, message) => {
      if (!element) return;
      element.dataset.state = state;
      element.textContent = message;
    };
    const updatePasswordChecks = () => {
      if (!newPasswordInput || !confirmPasswordInput) return;
      const newPassword = newPasswordInput.value;
      const confirmation = confirmPasswordInput.value;
      if (!newPassword) {
        setPasswordCheck(newPasswordCheck, 'neutral', i18n.passwordTooShort || 'Use at least 8 characters.');
        newPasswordInput.removeAttribute('aria-invalid');
      } else if (newPassword.length < 8) {
        setPasswordCheck(newPasswordCheck, 'invalid', i18n.passwordTooShort || 'Use at least 8 characters.');
        newPasswordInput.setAttribute('aria-invalid', 'true');
      } else {
        setPasswordCheck(newPasswordCheck, 'valid', i18n.passwordLengthValid || 'Password length is valid.');
        newPasswordInput.removeAttribute('aria-invalid');
      }

      if (!confirmation) {
        setPasswordCheck(
          confirmPasswordCheck,
          'neutral',
          i18n.passwordConfirmationEmpty || 'Enter the confirmation password.',
        );
        confirmPasswordInput.setCustomValidity('');
        confirmPasswordInput.removeAttribute('aria-invalid');
      } else if (confirmation !== newPassword) {
        const mismatchMessage = i18n.passwordsDoNotMatch || 'Passwords do not match.';
        setPasswordCheck(confirmPasswordCheck, 'invalid', mismatchMessage);
        confirmPasswordInput.setCustomValidity(mismatchMessage);
        confirmPasswordInput.setAttribute('aria-invalid', 'true');
      } else {
        setPasswordCheck(confirmPasswordCheck, 'valid', i18n.passwordsMatch || 'Passwords match.');
        confirmPasswordInput.setCustomValidity('');
        confirmPasswordInput.removeAttribute('aria-invalid');
      }
    };
    const resetPasswordVisibility = () => {
      visibilityButtons.forEach((button) => {
        const input = button.closest('.password-input-control')?.querySelector('input');
        if (input) input.type = 'password';
        button.setAttribute('aria-pressed', 'false');
        button.setAttribute('aria-label', button.dataset.showLabel || 'Show password');
      });
    };

    visibilityButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const input = button.closest('.password-input-control')?.querySelector('input');
        if (!input) return;
        const shouldShow = input.type === 'password';
        input.type = shouldShow ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(shouldShow));
        button.setAttribute(
          'aria-label',
          shouldShow ? (button.dataset.hideLabel || 'Hide password') : (button.dataset.showLabel || 'Show password'),
        );
      });
    });
    newPasswordInput?.addEventListener('input', updatePasswordChecks);
    confirmPasswordInput?.addEventListener('input', updatePasswordChecks);
    updatePasswordChecks();

    passwordChangeForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const scrollPosition = window.scrollY;
      const keepWindowPosition = () => setScrollPositionInstantly(scrollPosition);
      try { sessionStorage.removeItem(preservedScrollKey); } catch (_error) {}
      const submitButton = passwordChangeForm.querySelector('button[type="submit"]');
      const panel = passwordChangeForm.closest('.profile-panel');
      if (!submitButton || !panel) return;
      submitButton.disabled = true;
      try {
        const response = await fetch(passwordChangeForm.action, {
          method: 'POST',
          body: new FormData(passwordChangeForm),
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
        });
        const result = await response.json();
        panel.querySelectorAll('.profile-form-status').forEach((status) => status.remove());
        const status = document.createElement('div');
        status.className = `profile-form-status profile-form-status-${result.ok ? 'success' : 'error'}`;
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        const icon = document.createElement('span');
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = result.ok ? '✓' : '!';
        const message = document.createElement('p');
        message.textContent = result.message;
        status.append(icon, message);
        passwordChangeForm.insertAdjacentElement('afterend', status);
        if (result.ok) {
          passwordChangeForm.reset();
          resetPasswordVisibility();
          updatePasswordChecks();
        }
      } catch (_error) {
        panel.querySelectorAll('.profile-form-status').forEach((status) => status.remove());
        const status = document.createElement('div');
        status.className = 'profile-form-status profile-form-status-error';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        const icon = document.createElement('span');
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = '!';
        const message = document.createElement('p');
        message.textContent = i18n.profileUpdateFailed
          || 'The profile update could not be completed. Please try again.';
        status.append(icon, message);
        passwordChangeForm.insertAdjacentElement('afterend', status);
      } finally {
        submitButton.disabled = false;
        keepWindowPosition();
        requestAnimationFrame(() => requestAnimationFrame(keepWindowPosition));
      }
    });
  }

  try {
    const savedScroll = JSON.parse(sessionStorage.getItem(preservedScrollKey) || 'null');
    sessionStorage.removeItem(preservedScrollKey);
    if (savedScroll
      && savedScroll.path === window.location.pathname
      && Number.isFinite(savedScroll.position)
      && Date.now() - savedScroll.savedAt < 120000) {
      const anchor = savedScroll.anchorKey
        ? preserveScrollForms.find((form) => preserveScrollAnchorKey(form) === savedScroll.anchorKey)
        : null;
      const previousRestoration = history.scrollRestoration;
      history.scrollRestoration = 'manual';
      const restoreScrollPosition = () => {
        if (anchor && Number.isFinite(savedScroll.anchorTop)) {
          const drift = anchor.getBoundingClientRect().top - savedScroll.anchorTop;
          setScrollPositionInstantly(window.scrollY + drift);
        } else {
          setScrollPositionInstantly(savedScroll.position);
        }
      };
      restoreScrollPosition();
      requestAnimationFrame(() => requestAnimationFrame(restoreScrollPosition));
      window.addEventListener('load', () => {
        restoreScrollPosition();
        history.scrollRestoration = previousRestoration;
      }, { once: true });
    }
  } catch (_error) {
    try { sessionStorage.removeItem(preservedScrollKey); } catch (_storageError) {}
  }

  const navToggle = document.querySelector('.nav-toggle');
  const siteNav = document.querySelector('.site-nav');
  if (navToggle && siteNav) {
    navToggle.addEventListener('click', () => {
      const open = siteNav.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', String(open));
    });
  }

  document.querySelectorAll('.flash button').forEach((button) => {
    button.addEventListener('click', () => button.parentElement.remove());
  });

  const locationButton = document.querySelector('[data-use-location]');
  const nearbyForm = document.querySelector('[data-nearby-form]');
  const locationStatus = document.querySelector('[data-location-status]');
  if (locationButton && nearbyForm) {
    locationButton.addEventListener('click', () => {
      if (!navigator.geolocation) {
        locationStatus.textContent = i18n.locationUnsupported || 'Location is not supported by this browser.';
        return;
      }
      locationButton.disabled = true;
      locationButton.querySelector('span').textContent = i18n.finding || 'Finding you…';
      locationStatus.textContent = i18n.permissionPrompt || 'Your browser may ask for location permission.';
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          nearbyForm.querySelector('[data-latitude]').value = coords.latitude;
          nearbyForm.querySelector('[data-longitude]').value = coords.longitude;
          locationStatus.textContent = i18n.locationFound || 'Location found. Searching nearby reports…';
          nearbyForm.submit();
        },
        (error) => {
          const messages = {
            1: i18n.permissionDenied || 'Location access was declined. You can still search by keyword.',
            2: i18n.locationUnavailable || 'Your location is currently unavailable. Please try again.',
            3: i18n.locationTimeout || 'Location lookup timed out. Please try again.',
          };
          locationStatus.textContent = messages[error.code] || i18n.locationFailed || 'Could not get your location.';
          locationButton.disabled = false;
          locationButton.querySelector('span').textContent = i18n.useLocation || 'Use my location';
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
      );
    });
  }

  const counted = document.querySelector('[data-counted]');
  const charCount = document.querySelector('[data-char-count]');
  if (counted && charCount) {
    const updateCount = () => { charCount.textContent = `${counted.value.length.toLocaleString()} / 5,000`; };
    counted.addEventListener('input', updateCount);
    updateCount();
  }

  const formatLocalTimes = (root) => root.querySelectorAll('[data-local-time]').forEach((element) => {
    const value = element.querySelector('[data-local-time-value]');
    const timezone = element.querySelector('[data-local-timezone]');
    const instant = new Date(element.getAttribute('datetime'));
    if (!value || Number.isNaN(instant.getTime()) || typeof Intl === 'undefined') return;
    try {
      const locale = document.documentElement.lang || 'en-US';
      const dateOnly = element.dataset.localTimePrecision === 'date';
      const options = { year: 'numeric', month: '2-digit', day: '2-digit' };
      if (!dateOnly) Object.assign(options, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
      const parts = new Intl.DateTimeFormat(locale, options).formatToParts(instant);
      const part = (type) => parts.find((item) => item.type === type)?.value || '';
      value.textContent = `${part('year')}-${part('month')}-${part('day')}${dateOnly ? '' : ` ${part('hour')}:${part('minute')}`}`;
      if (timezone) {
        const zoneParts = new Intl.DateTimeFormat(locale, { timeZoneName: 'short' }).formatToParts(instant);
        timezone.textContent = zoneParts.find((item) => item.type === 'timeZoneName')?.value
          || Intl.DateTimeFormat().resolvedOptions().timeZone
          || 'UTC';
      }
    } catch (_error) {
      // Keep the server-rendered Cloudflare timezone or UTC fallback.
    }
  });
  formatLocalTimes(document);

  const reportGrid = document.querySelector('[data-report-grid]');
  const reportMore = document.querySelector('[data-report-more]');
  if (reportGrid && reportMore && 'IntersectionObserver' in window) {
    const moreLink = reportMore.querySelector('[data-report-more-link]');
    const moreStatus = reportMore.querySelector('[data-report-more-status]');
    const loadingLabel = reportMore.dataset.loadingLabel || 'Loading more reports…';
    const failedLabel = reportMore.dataset.failedLabel || 'More reports could not be loaded. Please try again.';
    let nextOffset = Number(reportMore.dataset.nextOffset) || 0;
    let loading = false;
    let finished = false;

    const setMoreStatus = (text, busy) => {
      moreStatus.textContent = '';
      if (busy) {
        const spinner = document.createElement('span');
        spinner.className = 'report-more-spinner';
        spinner.setAttribute('aria-hidden', 'true');
        moreStatus.appendChild(spinner);
      }
      moreStatus.appendChild(document.createTextNode(text));
    };

    const loadMoreReports = async () => {
      if (loading || finished) return;
      loading = true;
      reportMore.dataset.loading = 'true';
      setMoreStatus(loadingLabel, true);
      try {
        const url = new URL(reportMore.dataset.batchUrl, window.location.origin);
        url.searchParams.set('offset', String(nextOffset));
        const response = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error('Report batch request failed');
        const payload = await response.json();
        const batch = document.createElement('template');
        batch.innerHTML = payload.html || '';
        const added = batch.content.children.length;
        formatLocalTimes(batch.content);
        reportGrid.appendChild(batch.content);
        nextOffset = Number(payload.next_offset) || nextOffset + added;
        reportMore.dataset.nextOffset = String(nextOffset);
        if (moreLink) {
          const fallback = new URL(moreLink.href, window.location.origin);
          fallback.searchParams.set('offset', String(nextOffset));
          moreLink.href = fallback.toString();
        }
        // Reloading after a preference change must render the batches already
        // on screen, otherwise the page shrinks and the restored position is
        // meaningless.
        preserveScrollForms.forEach((form) => {
          const destination = form.querySelector('input[name="next"]');
          if (!destination) return;
          const target = new URL(destination.value || window.location.pathname, window.location.origin);
          target.searchParams.set('offset', String(nextOffset));
          destination.value = `${target.pathname}${target.search}`;
        });
        setMoreStatus('', false);
        if (!payload.has_more || !added) {
          finished = true;
          moreObserver.disconnect();
          if (reportMore.dataset.completeLabel && locationStatus) {
            locationStatus.textContent = reportMore.dataset.completeLabel;
          }
          reportMore.remove();
        } else {
          // Observers only report threshold crossings, so a sentinel still in
          // view after the append is re-observed to load the batch after it.
          moreObserver.unobserve(reportMore);
          moreObserver.observe(reportMore);
        }
      } catch (_error) {
        setMoreStatus(failedLabel, false);
      } finally {
        loading = false;
        delete reportMore.dataset.loading;
      }
    };

    const moreObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMoreReports();
    }, { rootMargin: '400px 0px' });
    moreObserver.observe(reportMore);
    if (moreLink) {
      moreLink.addEventListener('click', (event) => {
        event.preventDefault();
        loadMoreReports();
      });
    }
  }

  document.querySelectorAll('[data-hashtag-editor]').forEach((editor) => {
    const input = editor.querySelector('[data-hashtag-input]');
    const hidden = editor.querySelector('[data-hashtag-value]');
    const chips = editor.querySelector('[data-hashtag-chips]');
    const status = editor.parentElement.querySelector('[data-hashtag-status]');
    const suggestionButtons = [...editor.parentElement.querySelectorAll('[data-hashtag-suggestion]')];
    if (!input || !hidden || !chips || !status) return;

    const limit = Number(editor.dataset.hashtagLimit) || 10;
    const invalidMessage = editor.dataset.hashtagInvalid || 'Use 1 to 30 letters, numbers, or underscores per hashtag.';
    const limitMessage = editor.dataset.hashtagLimitMessage || 'Add no more than 10 hashtags.';
    const removeLabel = editor.dataset.hashtagRemoveLabel || 'Remove hashtag';
    const hashtags = [];
    const splitHashtags = (value) => value.split(/[\s,，]+/u).map((item) => item.replace(/^[#＃]+/u, '')).filter(Boolean);
    const sortHashtags = () => {
      hashtags.sort((first, second) => {
        const normalizedFirst = first.toLocaleLowerCase();
        const normalizedSecond = second.toLocaleLowerCase();
        if (normalizedFirst < normalizedSecond) return -1;
        if (normalizedFirst > normalizedSecond) return 1;
        return 0;
      });
    };
    const isValidHashtag = (hashtag) => {
      const characters = [...hashtag];
      return characters.length >= 1
        && characters.length <= 30
        && characters.every((character) => character === '_' || /[\p{L}\p{N}]/u.test(character));
    };
    const syncValue = () => {
      hidden.value = hashtags.map((hashtag) => `#${hashtag}`).join(' ');
    };
    const render = () => {
      chips.replaceChildren();
      hashtags.forEach((hashtag, index) => {
        const chip = document.createElement('span');
        chip.className = 'hashtag-editor-chip';
        const text = document.createElement('span');
        text.textContent = `#${hashtag}`;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.setAttribute('aria-label', `${removeLabel} #${hashtag}`);
        remove.textContent = '×';
        remove.addEventListener('click', () => {
          hashtags.splice(index, 1);
          status.textContent = '';
          syncValue();
          render();
          input.focus();
        });
        chip.append(text, remove);
        chips.append(chip);
      });
      const selected = new Set(hashtags.map((hashtag) => hashtag.toLowerCase()));
      suggestionButtons.forEach((button) => {
        const isSelected = selected.has(button.dataset.hashtagSuggestion.toLowerCase());
        button.disabled = isSelected || hashtags.length >= limit;
        button.setAttribute('aria-pressed', String(isSelected));
      });
    };
    const commit = () => {
      const candidates = splitHashtags(input.value);
      if (!candidates.length) {
        input.value = '';
        status.textContent = '';
        return true;
      }
      if (candidates.some((hashtag) => !isValidHashtag(hashtag))) {
        status.textContent = invalidMessage;
        return false;
      }
      const seen = new Set(hashtags.map((hashtag) => hashtag.toLowerCase()));
      const additions = candidates.filter((hashtag) => {
        const normalized = hashtag.toLowerCase();
        if (seen.has(normalized)) return false;
        seen.add(normalized);
        return true;
      });
      if (hashtags.length + additions.length > limit) {
        status.textContent = limitMessage;
        return false;
      }
      hashtags.push(...additions);
      sortHashtags();
      input.value = '';
      status.textContent = '';
      syncValue();
      render();
      return true;
    };

    const initialValue = input.value;
    input.removeAttribute('name');
    hidden.name = 'hashtags';
    input.value = initialValue;
    commit();
    input.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
        event.preventDefault();
        commit();
      } else if (event.key === 'Backspace' && !input.value && hashtags.length) {
        hashtags.pop();
        status.textContent = '';
        syncValue();
        render();
      }
    });
    input.addEventListener('input', () => { status.textContent = ''; });
    input.addEventListener('blur', commit);
    suggestionButtons.forEach((button) => {
      button.addEventListener('mousedown', (event) => event.preventDefault());
      button.addEventListener('click', () => {
        if (input.value.trim() && !commit()) {
          input.focus();
          return;
        }
        input.value = button.dataset.hashtagSuggestion;
        commit();
        input.focus();
      });
    });
    input.form?.addEventListener('submit', (event) => {
      if (!commit()) {
        event.preventDefault();
        input.focus();
      }
    });
  });

  const onlineShop = document.querySelector('[data-online-shop]');
  const shopNameInput = document.querySelector('[data-shop-name]');
  const addressInput = document.querySelector('[data-shop-address]');
  const placeIdInput = document.querySelector('[data-place-id]');
  const addressEnUsInput = document.querySelector('[data-place-address-en-us]');
  const addressZhTwInput = document.querySelector('[data-place-address-zh-tw]');
  addressInput?.addEventListener('input', () => {
    if (placeIdInput) placeIdInput.value = '';
    if (addressEnUsInput) addressEnUsInput.value = '';
    if (addressZhTwInput) addressZhTwInput.value = '';
  });
  const syncOnlineShop = () => {
    if (!onlineShop) return;
    document.querySelectorAll('[data-address-dependent]').forEach((element) => {
      element.hidden = onlineShop.checked;
    });
    if (addressInput) {
      addressInput.disabled = onlineShop.checked;
      addressInput.required = !onlineShop.checked;
    }
  };
  if (onlineShop) {
    onlineShop.addEventListener('change', syncOnlineShop);
    syncOnlineShop();
  }

  const similarReportCheck = document.querySelector('[data-similar-report-check]');
  const similarReportStatus = similarReportCheck?.querySelector('[data-similar-report-status]');
  const similarReportCount = similarReportCheck?.querySelector('[data-similar-report-count]');
  const similarReportDialog = document.querySelector('[data-similar-report-dialog]');
  const similarReportDialogStatus = similarReportDialog?.querySelector('[data-similar-report-dialog-status]');
  const similarReportList = similarReportDialog?.querySelector('[data-similar-report-list]');
  const similarReportResults = similarReportDialog?.querySelector('[data-similar-report-results]');
  const similarReportViewer = similarReportDialog?.querySelector('[data-similar-report-viewer]');
  const similarReportFrame = similarReportDialog?.querySelector('[data-similar-report-frame]');
  if (similarReportCheck && similarReportStatus && similarReportDialogStatus && similarReportResults && shopNameInput) {
    let similarReportTimer;
    let similarReportRequest;
    const setSimilarReportState = (state, message) => {
      similarReportCheck.dataset.state = state;
      similarReportStatus.textContent = message;
      similarReportDialogStatus.textContent = message;
    };
    const renderSimilarReports = (reports) => {
      similarReportResults.replaceChildren();
      if (similarReportCount) similarReportCount.textContent = String(reports.length);
      reports.forEach((report) => {
        const link = document.createElement('a');
        link.className = 'similar-report-result';
        link.href = report.url;
        link.addEventListener('click', (event) => {
          if (!similarReportFrame || !similarReportViewer || !similarReportList) return;
          event.preventDefault();
          similarReportFrame.title = report.name;
          similarReportFrame.src = report.url;
          similarReportList.hidden = true;
          similarReportViewer.hidden = false;
        });
        const copy = document.createElement('span');
        const name = document.createElement('strong');
        name.textContent = report.name;
        const location = document.createElement('small');
        location.textContent = report.is_online
          ? similarReportCheck.dataset.onlineLabel
          : report.address;
        copy.append(name, location);
        const date = document.createElement('small');
        date.className = 'similar-report-date';
        date.textContent = `${similarReportCheck.dataset.reportedLabel} ${report.reported_at}`;
        const arrow = document.createElement('span');
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '→';
        link.append(copy, date, arrow);
        similarReportResults.append(link);
      });
    };
    const checkSimilarReports = async () => {
      const name = shopNameInput.value.trim();
      const address = onlineShop?.checked ? '' : addressInput?.value.trim() || '';
      if (name.length < 2 && address.length < 4 && !placeIdInput?.value) {
        similarReportRequest?.abort();
        renderSimilarReports([]);
        setSimilarReportState('idle', similarReportCheck.dataset.idleMessage);
        return;
      }

      similarReportRequest?.abort();
      similarReportRequest = new AbortController();
      renderSimilarReports([]);
      setSimilarReportState('loading', similarReportCheck.dataset.loadingMessage);
      const url = new URL(similarReportCheck.dataset.similarReportUrl, window.location.origin);
      url.searchParams.set('name', name);
      if (address) url.searchParams.set('address', address);
      if (placeIdInput?.value) url.searchParams.set('place_id', placeIdInput.value);
      if (!onlineShop?.checked && document.querySelector('[data-place-lat]')?.value) {
        url.searchParams.set('lat', document.querySelector('[data-place-lat]').value);
      }
      if (!onlineShop?.checked && document.querySelector('[data-place-lng]')?.value) {
        url.searchParams.set('lng', document.querySelector('[data-place-lng]').value);
      }
      if (similarReportCheck.dataset.excludeGuid) {
        url.searchParams.set('exclude', similarReportCheck.dataset.excludeGuid);
      }
      try {
        const response = await fetch(url, {
          headers: { Accept: 'application/json' },
          signal: similarReportRequest.signal,
        });
        if (!response.ok) throw new Error('Similar-report check failed');
        const payload = await response.json();
        renderSimilarReports(payload.reports || []);
        if (payload.reports?.length) {
          const message = payload.reports.length === 1
            ? similarReportCheck.dataset.foundOneMessage
            : similarReportCheck.dataset.foundManyMessage.replace('{count}', payload.reports.length);
          setSimilarReportState('matches', message);
        } else {
          setSimilarReportState('empty', similarReportCheck.dataset.emptyMessage);
        }
      } catch (error) {
        if (error.name === 'AbortError') return;
        renderSimilarReports([]);
        setSimilarReportState('error', similarReportCheck.dataset.errorMessage);
      }
    };
    const scheduleSimilarReportCheck = () => {
      clearTimeout(similarReportTimer);
      similarReportTimer = setTimeout(checkSimilarReports, 450);
    };
    shopNameInput.addEventListener('input', scheduleSimilarReportCheck);
    addressInput?.addEventListener('input', scheduleSimilarReportCheck);
    onlineShop?.addEventListener('change', scheduleSimilarReportCheck);
    document.addEventListener('shopalert:place-selected', scheduleSimilarReportCheck);
    if (shopNameInput.value.trim() || addressInput?.value.trim()) {
      scheduleSimilarReportCheck();
    }
    const resetSimilarReportViewer = () => {
      if (similarReportFrame) {
        similarReportFrame.removeAttribute('src');
        similarReportFrame.title = similarReportFrame.dataset.defaultTitle || 'Existing report preview';
      }
      if (similarReportList) similarReportList.hidden = false;
      if (similarReportViewer) similarReportViewer.hidden = true;
    };
    if (similarReportFrame) similarReportFrame.dataset.defaultTitle = similarReportFrame.title;
    document.querySelector('[data-similar-report-dialog-open]')?.addEventListener('click', () => {
      if (typeof similarReportDialog?.showModal === 'function' && !similarReportDialog.open) {
        resetSimilarReportViewer();
        similarReportDialog.showModal();
      }
    });
    similarReportDialog?.querySelector('[data-similar-report-dialog-close]')?.addEventListener('click', () => similarReportDialog.close());
    similarReportDialog?.querySelector('[data-similar-report-back]')?.addEventListener('click', resetSimilarReportViewer);
    similarReportDialog?.addEventListener('click', (event) => {
      if (event.target === similarReportDialog) similarReportDialog.close();
    });
    similarReportDialog?.addEventListener('close', resetSimilarReportViewer);
  }

  const applyMediaPreviewRotation = (media, preview, rotation) => {
    if (!media || !preview) return;
    const quarterTurn = rotation % 180 !== 0;
    const scale = quarterTurn
      ? Math.min(
        preview.clientWidth / preview.clientHeight,
        preview.clientHeight / preview.clientWidth,
      )
      : 1;
    media.style.transform = `rotate(${rotation}deg) scale(${scale})`;
  };

  document.querySelectorAll('[data-existing-media]').forEach((item) => {
    const preview = item.querySelector('.existing-media-preview');
    const media = item.querySelector('[data-existing-media-element]');
    const rotationInput = item.querySelector('[data-existing-media-rotation]');
    if (!preview || !media || !rotationInput) return;
    const updateRotation = () => {
      applyMediaPreviewRotation(media, preview, Number(rotationInput.value) || 0);
    };
    item.querySelectorAll('[data-existing-media-rotate]').forEach((button) => {
      button.addEventListener('click', () => {
        const rotation = Number(rotationInput.value) || 0;
        const amount = Number(button.dataset.existingMediaRotate) || 0;
        rotationInput.value = String((rotation + amount + 360) % 360);
        updateRotation();
      });
    });
    media.addEventListener('load', updateRotation);
    media.addEventListener('loadedmetadata', updateRotation);
    if (typeof ResizeObserver === 'function') {
      item.mediaRotationObserver = new ResizeObserver(updateRotation);
      item.mediaRotationObserver.observe(preview);
    }
    requestAnimationFrame(updateRotation);
  });

  const fileInput = document.querySelector('[data-proof-input]');
  const uploadZone = document.querySelector('[data-upload-zone]');
  const previews = document.querySelector('[data-upload-previews]');
  const mediaOrderInput = document.querySelector('[data-media-order]');
  if (fileInput && uploadZone && previews && mediaOrderInput) {
    const reportForm = fileInput.closest('[data-report-form]');
    const uploadSizeStatus = reportForm?.querySelector('[data-upload-size-status]');
    const maxUploadBytes = Number(reportForm?.dataset.maxUploadBytes) || 0;
    const selectedFiles = [];
    const existingItems = [...previews.querySelectorAll('[data-media-order-token]')];
    let mediaOrder = existingItems.map((item) => item.dataset.mediaOrderToken);
    let nextUploadToken = 0;
    const updatePreviewRotation = (selectedFile) => {
      const media = selectedFile.previewElement;
      const preview = media?.parentElement;
      applyMediaPreviewRotation(media, preview, selectedFile.rotation);
    };
    const resizeObserver = typeof ResizeObserver === 'function'
      ? new ResizeObserver(() => selectedFiles.forEach(updatePreviewRotation))
      : null;
    const syncFileInput = () => {
      const transfer = new DataTransfer();
      selectedFiles.forEach(({ file }) => transfer.items.add(file));
      fileInput.files = transfer.files;
    };
    const syncMediaOrder = () => {
      mediaOrderInput.value = JSON.stringify(mediaOrder);
    };
    const formatUploadSize = (bytes) => {
      const megabytes = bytes / 1024 / 1024;
      return `${megabytes.toFixed(megabytes >= 10 ? 1 : 2)} MB`;
    };
    const validateUploadSize = () => {
      const selectedBytes = selectedFiles.reduce((total, { file }) => total + file.size, 0);
      const tooLarge = maxUploadBytes > 0 && selectedBytes > maxUploadBytes;
      if (uploadSizeStatus) {
        uploadSizeStatus.textContent = tooLarge
          ? (i18n.uploadTooLarge || 'Selected files use {selected}; the upload limit is {limit}.')
            .replace('{selected}', formatUploadSize(selectedBytes))
            .replace('{limit}', formatUploadSize(maxUploadBytes))
          : '';
      }
      uploadZone.classList.toggle('upload-too-large', tooLarge);
      if (tooLarge) fileInput.setAttribute('aria-invalid', 'true');
      else fileInput.removeAttribute('aria-invalid');
      return !tooLarge;
    };
    const updateMoveButtons = () => {
      previews.querySelectorAll('[data-media-order-token]').forEach((item) => {
        const index = mediaOrder.indexOf(item.dataset.mediaOrderToken);
        const earlier = item.querySelector('[data-media-move="-1"]');
        const later = item.querySelector('[data-media-move="1"]');
        if (earlier) earlier.disabled = index <= 0;
        if (later) later.disabled = index < 0 || index >= mediaOrder.length - 1;
      });
    };
    const moveMedia = (token, amount) => {
      const index = mediaOrder.indexOf(token);
      const destination = index + amount;
      if (index < 0 || destination < 0 || destination >= mediaOrder.length) return;
      [mediaOrder[index], mediaOrder[destination]] = [
        mediaOrder[destination],
        mediaOrder[index],
      ];
      selectedFiles.sort(
        (left, right) => mediaOrder.indexOf(left.token) - mediaOrder.indexOf(right.token),
      );
      syncFileInput();
      renderFiles();
      validateUploadSize();
    };
    const bindMoveControls = (item) => {
      item.querySelectorAll('[data-media-move]').forEach((button) => {
        button.addEventListener('click', () => {
          moveMedia(item.dataset.mediaOrderToken, Number(button.dataset.mediaMove));
        });
      });
    };
    const removeFile = (selectedFile) => {
      const index = selectedFiles.indexOf(selectedFile);
      if (index < 0) return;
      selectedFiles.splice(index, 1);
      mediaOrder = mediaOrder.filter((token) => token !== selectedFile.token);
      if (selectedFile.previewUrl) URL.revokeObjectURL(selectedFile.previewUrl);
      syncFileInput();
      renderFiles();
      validateUploadSize();
    };
    const renderFiles = () => {
      resizeObserver?.disconnect();
      previews.replaceChildren();
      const renderedItems = new Map(
        existingItems.map((item) => [item.dataset.mediaOrderToken, item]),
      );
      selectedFiles.forEach((selectedFile) => {
        const { file } = selectedFile;
        const row = document.createElement('div');
        row.className = 'upload-file';
        row.dataset.mediaOrderToken = selectedFile.token;
        const preview = document.createElement('span');
        preview.className = 'upload-file-preview';
        if (!selectedFile.previewUrl) selectedFile.previewUrl = URL.createObjectURL(file);
        if (file.type.startsWith('video/')) {
          preview.classList.add('is-video');
          const video = document.createElement('video');
          video.src = `${selectedFile.previewUrl}#t=0.1`;
          video.muted = true;
          video.preload = 'metadata';
          video.playsInline = true;
          selectedFile.previewElement = video;
          const playIcon = document.createElement('i');
          playIcon.textContent = '▶';
          playIcon.setAttribute('aria-hidden', 'true');
          preview.append(video, playIcon);
        } else {
          const image = document.createElement('img');
          image.src = selectedFile.previewUrl;
          image.alt = '';
          selectedFile.previewElement = image;
          preview.append(image);
        }
        selectedFile.previewElement.addEventListener(
          'loadedmetadata',
          () => updatePreviewRotation(selectedFile),
        );
        selectedFile.previewElement.addEventListener(
          'load',
          () => updatePreviewRotation(selectedFile),
        );
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'upload-file-remove';
        removeButton.textContent = '×';
        removeButton.title = i18n.removeFile || 'Remove file';
        removeButton.setAttribute('aria-label', `${i18n.removeFile || 'Remove file'}: ${file.name}`);
        removeButton.addEventListener('click', () => removeFile(selectedFile));
        preview.append(removeButton);
        const rotationControls = document.createElement('span');
        rotationControls.className = 'upload-file-rotation';
        const rotationInput = document.createElement('input');
        rotationInput.type = 'hidden';
        rotationInput.name = 'proof_rotation';
        rotationInput.value = String(selectedFile.rotation);
        const rotateButton = (amount, label, arrow) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = arrow;
          button.title = label;
          button.setAttribute('aria-label', `${label}: ${file.name}`);
          button.addEventListener('click', () => {
            selectedFile.rotation = (selectedFile.rotation + amount + 360) % 360;
            rotationInput.value = String(selectedFile.rotation);
            updatePreviewRotation(selectedFile);
          });
          return button;
        };
        rotationControls.append(
          rotateButton(-90, i18n.rotateLeft || 'Rotate left', '↶'),
          rotateButton(90, i18n.rotateRight || 'Rotate right', '↷'),
        );
        preview.append(rotationControls);
        const reorderControls = document.createElement('span');
        reorderControls.className = 'media-reorder-controls';
        const moveButton = (amount, label, arrow) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = arrow;
          button.title = label;
          button.setAttribute('aria-label', `${label}: ${file.name}`);
          button.dataset.mediaMove = String(amount);
          return button;
        };
        reorderControls.append(
          moveButton(-1, i18n.moveUp || 'Move up', '↑'),
          moveButton(1, i18n.moveDown || 'Move down', '↓'),
        );
        preview.append(reorderControls);
        const dragHandle = document.createElement('span');
        dragHandle.className = 'media-drag-handle';
        dragHandle.draggable = true;
        dragHandle.dataset.mediaDragHandle = '';
        dragHandle.title = i18n.dragToReorder || 'Drag to reorder';
        dragHandle.textContent = '⠿';
        dragHandle.setAttribute('aria-hidden', 'true');
        preview.append(dragHandle);
        const details = document.createElement('div');
        details.className = 'upload-file-details';
        const meta = document.createElement('div');
        meta.className = 'upload-file-meta';
        const sourceName = document.createElement('strong');
        sourceName.textContent = file.name;
        const size = document.createElement('span');
        size.textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB`;
        meta.append(sourceName, size);
        const nameLabel = document.createElement('label');
        nameLabel.className = 'media-name-field';
        const nameText = document.createElement('span');
        nameText.textContent = i18n.mediaName || 'Media filename';
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.name = 'proof_name';
        nameInput.value = selectedFile.displayName;
        nameInput.maxLength = 255;
        nameInput.required = true;
        nameInput.addEventListener('input', () => {
          selectedFile.displayName = nameInput.value;
        });
        nameLabel.append(nameText, nameInput);
        const tokenInput = document.createElement('input');
        tokenInput.type = 'hidden';
        tokenInput.name = 'proof_token';
        tokenInput.value = selectedFile.token;
        details.append(meta, nameLabel, rotationInput, tokenInput);
        row.append(preview, details);
        bindMoveControls(row);
        renderedItems.set(selectedFile.token, row);
        resizeObserver?.observe(preview);
        requestAnimationFrame(() => updatePreviewRotation(selectedFile));
      });
      mediaOrder = mediaOrder.filter((token) => renderedItems.has(token));
      renderedItems.forEach((_item, token) => {
        if (!mediaOrder.includes(token)) mediaOrder.push(token);
      });
      previews.append(...mediaOrder.map((token) => renderedItems.get(token)));
      syncMediaOrder();
      updateMoveButtons();
    };
    const appendFiles = (files) => {
      [...files].forEach((file) => {
        const token = `new:${Date.now().toString(36)}-${nextUploadToken}`;
        nextUploadToken += 1;
        selectedFiles.push({
          file,
          displayName: file.name,
          rotation: 0,
          token,
        });
        mediaOrder.push(token);
      });
      syncFileInput();
      renderFiles();
      validateUploadSize();
    };
    existingItems.forEach(bindMoveControls);
    renderFiles();
    let draggingToken = null;
    const clearDropTargets = () => {
      previews.querySelectorAll('.is-dragging, .is-drop-before, .is-drop-after').forEach(
        (item) => item.classList.remove('is-dragging', 'is-drop-before', 'is-drop-after'),
      );
    };
    const dropAfterItem = (event, item) => {
      const bounds = item.getBoundingClientRect();
      const horizontalOffset = (event.clientX - bounds.left) / bounds.width - 0.5;
      const verticalOffset = (event.clientY - bounds.top) / bounds.height - 0.5;
      return Math.abs(verticalOffset) > Math.abs(horizontalOffset)
        ? verticalOffset > 0
        : horizontalOffset > 0;
    };
    previews.addEventListener('dragstart', (event) => {
      const handle = event.target.closest('[data-media-drag-handle]');
      const item = handle?.closest('[data-media-order-token]');
      if (!item) {
        event.preventDefault();
        return;
      }
      draggingToken = item.dataset.mediaOrderToken;
      item.classList.add('is-dragging');
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', draggingToken);
      }
    });
    previews.addEventListener('dragover', (event) => {
      if (!draggingToken) return;
      const item = event.target.closest('[data-media-order-token]');
      if (!item || item.dataset.mediaOrderToken === draggingToken) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
      previews.querySelectorAll('.is-drop-before, .is-drop-after').forEach(
        (candidate) => candidate.classList.remove('is-drop-before', 'is-drop-after'),
      );
      item.classList.add(dropAfterItem(event, item) ? 'is-drop-after' : 'is-drop-before');
    });
    previews.addEventListener('drop', (event) => {
      if (!draggingToken) return;
      const item = event.target.closest('[data-media-order-token]');
      if (!item || item.dataset.mediaOrderToken === draggingToken) {
        clearDropTargets();
        draggingToken = null;
        return;
      }
      event.preventDefault();
      const targetToken = item.dataset.mediaOrderToken;
      const reordered = mediaOrder.filter((token) => token !== draggingToken);
      let destination = reordered.indexOf(targetToken);
      if (dropAfterItem(event, item)) destination += 1;
      reordered.splice(destination, 0, draggingToken);
      mediaOrder = reordered;
      selectedFiles.sort(
        (left, right) => mediaOrder.indexOf(left.token) - mediaOrder.indexOf(right.token),
      );
      syncFileInput();
      draggingToken = null;
      clearDropTargets();
      renderFiles();
    });
    previews.addEventListener('dragend', () => {
      draggingToken = null;
      clearDropTargets();
    });
    previews.addEventListener('dragleave', (event) => {
      if (!previews.contains(event.relatedTarget)) {
        previews.querySelectorAll('.is-drop-before, .is-drop-after').forEach(
          (item) => item.classList.remove('is-drop-before', 'is-drop-after'),
        );
      }
    });
    fileInput.addEventListener('change', () => appendFiles(fileInput.files));
    ['dragenter', 'dragover'].forEach((type) => uploadZone.addEventListener(type, (event) => {
      event.preventDefault();
      uploadZone.classList.add('dragover');
    }));
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', (event) => {
      event.preventDefault();
      uploadZone.classList.remove('dragover');
      appendFiles(event.dataTransfer?.files || []);
    });
    reportForm?.addEventListener('submit', (event) => {
      if (validateUploadSize()) return;
      event.preventDefault();
      uploadZone.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  document.querySelectorAll('[data-related-shop-editor]').forEach((relatedShopEditor) => {
    const list = relatedShopEditor.querySelector('[data-related-shop-list]');
    const searchInput = relatedShopEditor.querySelector('[data-related-shop-search]');
    const results = relatedShopEditor.querySelector('[data-related-shop-results]');
    const status = relatedShopEditor.querySelector('[data-related-shop-status]');
    const manualName = relatedShopEditor.querySelector('[data-related-shop-manual-name]');
    const manualAddress = relatedShopEditor.querySelector('[data-related-shop-manual-address]');
    const manualAdd = relatedShopEditor.querySelector('[data-related-shop-manual-add]');
    if (!list || !searchInput || !results || !status || !manualName || !manualAddress || !manualAdd) return;

    const data = relatedShopEditor.dataset;
    const limit = Number(data.relatedShopLimit) || 10;
    let entries = [];
    try {
      entries = JSON.parse(data.relatedShopEntries || '[]');
    } catch (error) {
      entries = [];
    }

    const entryKey = (entry) => (entry.guid
      ? `report:${entry.guid}`
      : `shop:${(entry.name || '').toLowerCase()}|${(entry.address || '').toLowerCase()}`);
    const entryLabel = (entry) => {
      const source = entry.guid ? data.reportedLabel : data.manualLabel;
      const detail = entry.address || (entry.is_online ? data.onlineLabel : '');
      return detail ? `${source} · ${detail}` : source;
    };
    const hiddenInput = (name, value) => {
      const field = document.createElement('input');
      field.type = 'hidden';
      field.name = name;
      field.value = value || '';
      return field;
    };
    const render = () => {
      list.replaceChildren();
      entries.forEach((entry, index) => {
        const item = document.createElement('li');
        item.className = 'related-shop-item';
        const copy = document.createElement('span');
        copy.className = 'related-shop-copy';
        const name = document.createElement('strong');
        name.textContent = entry.name;
        const label = document.createElement('small');
        label.textContent = entryLabel(entry);
        copy.append(name, label);
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'related-shop-remove';
        remove.textContent = '×';
        remove.setAttribute('aria-label', `${data.relatedShopRemoveLabel}: ${entry.name}`);
        remove.addEventListener('click', () => {
          entries.splice(index, 1);
          status.textContent = '';
          render();
        });
        item.append(
          hiddenInput('related_shop_guid', entry.guid),
          hiddenInput('related_shop_name', entry.guid ? '' : entry.name),
          hiddenInput('related_shop_address', entry.guid ? '' : entry.address),
          copy,
          remove,
        );
        list.append(item);
      });
    };
    const addEntry = (entry) => {
      if (entries.length >= limit) {
        status.textContent = data.relatedShopLimitMessage;
        return false;
      }
      if (entries.some((existing) => entryKey(existing) === entryKey(entry))) {
        status.textContent = data.relatedShopDuplicateMessage;
        return false;
      }
      entries.push(entry);
      status.textContent = '';
      render();
      return true;
    };

    let searchTimer;
    let searchRequest;
    const renderResults = (reports) => {
      results.replaceChildren();
      results.hidden = !reports.length;
      reports.forEach((report) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'related-shop-result';
        const name = document.createElement('strong');
        name.textContent = report.name;
        const detail = document.createElement('small');
        detail.textContent = report.is_online ? data.onlineLabel : report.address;
        const arrow = document.createElement('span');
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '+';
        option.append(name, detail, arrow);
        option.addEventListener('click', () => {
          if (!addEntry({
            guid: report.guid,
            name: report.name,
            address: report.address,
            is_online: report.is_online,
          })) return;
          searchInput.value = '';
          renderResults([]);
        });
        results.append(option);
      });
    };
    const searchReports = async () => {
      const term = searchInput.value.trim();
      if (term.length < 2) {
        searchRequest?.abort();
        renderResults([]);
        status.textContent = '';
        return;
      }
      searchRequest?.abort();
      searchRequest = new AbortController();
      status.textContent = data.relatedShopLoadingMessage;
      const url = new URL(data.relatedShopSearchUrl, window.location.origin);
      url.searchParams.set('q', term);
      if (data.relatedShopExcludeGuid) url.searchParams.set('exclude', data.relatedShopExcludeGuid);
      try {
        const response = await fetch(url, {
          headers: { Accept: 'application/json' },
          signal: searchRequest.signal,
        });
        if (!response.ok) throw new Error('Related-shop search failed');
        const payload = await response.json();
        const reports = payload.reports || [];
        renderResults(reports);
        status.textContent = reports.length ? '' : data.relatedShopEmptyMessage;
      } catch (error) {
        if (error.name === 'AbortError') return;
        renderResults([]);
        status.textContent = data.relatedShopErrorMessage;
      }
    };

    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(searchReports, 350);
    });
    searchInput.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      clearTimeout(searchTimer);
      searchReports();
    });
    const addManualEntry = () => {
      const name = manualName.value.trim();
      const address = manualAddress.value.trim();
      if ([...name].length < 2 || [...name].length > 180) {
        status.textContent = data.relatedShopNameMessage;
        manualName.focus();
        return;
      }
      if (!addEntry({ guid: '', name, address, is_online: false })) return;
      manualName.value = '';
      manualAddress.value = '';
      manualName.focus();
    };
    manualAdd.addEventListener('click', addManualEntry);
    [manualName, manualAddress].forEach((field) => field.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229 || event.key !== 'Enter') return;
      event.preventDefault();
      addManualEntry();
    }));
    render();
  });

  const formProgress = document.querySelector('[data-form-progress]');
  if (formProgress) {
    const progressItems = [...formProgress.querySelectorAll('[data-form-progress-step]')];
    const formSteps = [...document.querySelectorAll('[data-form-step]')];
    let progressFrame;
    const updateFormProgress = () => {
      progressFrame = undefined;
      const trackingLine = Math.min(window.innerHeight * 0.35, 260);
      let activeStep = formSteps[0]?.dataset.formStep;
      formSteps.forEach((section) => {
        if (section.getBoundingClientRect().top <= trackingLine) activeStep = section.dataset.formStep;
      });
      progressItems.forEach((item) => {
        const active = item.dataset.formProgressStep === activeStep;
        item.classList.toggle('active', active);
        if (active) item.setAttribute('aria-current', 'step');
        else item.removeAttribute('aria-current');
      });
    };
    const scheduleFormProgressUpdate = () => {
      if (progressFrame) return;
      progressFrame = window.requestAnimationFrame(updateFormProgress);
    };
    window.addEventListener('scroll', scheduleFormProgressUpdate, { passive: true });
    window.addEventListener('resize', scheduleFormProgressUpdate);
    updateFormProgress();
  }

  document.querySelectorAll('[data-evidence-gallery]').forEach((gallery) => {
    const slides = [...gallery.querySelectorAll('[data-evidence-slide]')];
    const thumbnails = [...gallery.querySelectorAll('[data-evidence-thumbnail]')];
    const index = gallery.querySelector('[data-evidence-index]');
    const indexCurrent = gallery.querySelector('[data-evidence-index-current]');
    thumbnails.forEach((thumbnail) => {
      thumbnail.addEventListener('click', () => {
        const selectedIndex = thumbnail.dataset.evidenceThumbnail;
        const position = Number(selectedIndex) + 1;
        slides.forEach((slide) => {
          const selected = slide.dataset.evidenceSlide === selectedIndex;
          slide.hidden = !selected;
          slide.classList.toggle('is-active', selected);
          if (!selected) slide.querySelector('video')?.pause();
        });
        thumbnails.forEach((item) => {
          const selected = item === thumbnail;
          item.classList.toggle('is-active', selected);
          item.setAttribute('aria-pressed', String(selected));
        });
        if (indexCurrent) indexCurrent.textContent = String(position);
        if (index) {
          index.setAttribute(
            'aria-label',
            `${index.dataset.indexLabel || 'Media item'} ${position} / ${slides.length}`,
          );
        }
        thumbnail.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      });
    });
  });

  const lightbox = document.querySelector('[data-image-lightbox]');
  const lightboxImage = lightbox?.querySelector('[data-lightbox-image]');
  const lightboxCaption = lightbox?.querySelector('[data-lightbox-caption]');
  if (lightbox && lightboxImage && lightboxCaption) {
    document.querySelectorAll('[data-evidence-lightbox]').forEach((link) => {
      link.addEventListener('click', (event) => {
        if (typeof lightbox.showModal !== 'function') return;
        event.preventDefault();
        lightboxImage.src = link.href;
        lightboxImage.alt = link.dataset.imageAlt || '';
        lightboxCaption.textContent = link.dataset.imageAlt || '';
        lightbox.showModal();
      });
    });
    const closeLightbox = () => lightbox.close();
    lightbox.querySelector('[data-lightbox-close]')?.addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', (event) => {
      if (event.target === lightbox) closeLightbox();
    });
    lightbox.addEventListener('close', () => {
      lightboxImage.removeAttribute('src');
      lightboxImage.alt = '';
      lightboxCaption.textContent = '';
    });
  }

  const linkPreviewDialog = document.querySelector('[data-link-preview-dialog]');
  const linkPreviewImage = linkPreviewDialog?.querySelector('[data-link-preview-image]');
  const linkPreviewLoading = linkPreviewDialog?.querySelector('[data-link-preview-loading]');
  const linkPreviewError = linkPreviewDialog?.querySelector('[data-link-preview-error]');
  const linkPreviewStatus = linkPreviewDialog?.querySelector('[data-link-preview-status]');
  const linkPreviewHost = linkPreviewDialog?.querySelector('[data-link-preview-host]');
  const linkPreviewUrl = linkPreviewDialog?.querySelector('[data-link-preview-url]');
  const linkPreviewContinue = linkPreviewDialog?.querySelector('[data-link-preview-continue]');
  let linkPreviewController;
  let linkPreviewObjectUrl;
  document.querySelectorAll('[data-controversy-link]').forEach((link) => {
    link.addEventListener('click', async (event) => {
      event.preventDefault();
      if (!linkPreviewDialog || typeof linkPreviewDialog.showModal !== 'function') {
        try {
          const response = await fetch(link.dataset.previewUrl, { credentials: 'same-origin' });
          if (!response.ok) throw new Error('Link check failed');
          if (window.confirm(i18n.externalLinkConfirm || 'This link opens an external website. Do you want to continue?')) {
            window.open(link.href, '_blank', 'noopener,noreferrer');
          }
        } catch (_error) {
          window.alert(i18n.linkCheckFailed || 'The safety check or screenshot failed. ShopAlert blocked this link.');
        }
        return;
      }
      const destination = new URL(link.href);
      linkPreviewController?.abort();
      linkPreviewController = new AbortController();
      if (linkPreviewObjectUrl) URL.revokeObjectURL(linkPreviewObjectUrl);
      linkPreviewObjectUrl = undefined;
      linkPreviewHost.textContent = destination.hostname;
      linkPreviewUrl.textContent = destination.href;
      linkPreviewContinue.removeAttribute('href');
      linkPreviewContinue.setAttribute('aria-disabled', 'true');
      linkPreviewImage.hidden = true;
      linkPreviewError.hidden = true;
      linkPreviewStatus.hidden = true;
      linkPreviewLoading.hidden = false;
      linkPreviewDialog.showModal();
      try {
        const response = await fetch(link.dataset.previewUrl, {
          credentials: 'same-origin',
          signal: linkPreviewController.signal,
        });
        if (!response.ok) {
          const message = response.status === 403
            ? (i18n.linkCheckMalicious || 'Cloudflare flagged this link as potentially malicious. ShopAlert blocked it.')
            : (i18n.linkCheckFailed || 'The safety check or screenshot failed. ShopAlert blocked this link.');
          throw new Error(message);
        }
        const check = response.headers.get('X-ShopAlert-Link-Check');
        linkPreviewStatus.textContent = check === 'cloudflare-no-known-threat'
          ? (i18n.linkCheckClean || 'Cloudflare URL Scanner found no known threat at scan time. This is not a guarantee.')
          : (i18n.linkCheckNotConfigured || 'Cloudflare URL Scanner is not configured; only technical URL checks were applied.');
        linkPreviewStatus.hidden = false;
        linkPreviewObjectUrl = URL.createObjectURL(await response.blob());
        linkPreviewImage.src = linkPreviewObjectUrl;
        linkPreviewContinue.href = destination.href;
        linkPreviewContinue.setAttribute('aria-disabled', 'false');
      } catch (error) {
        if (error.name === 'AbortError') return;
        linkPreviewLoading.hidden = true;
        linkPreviewImage.hidden = true;
        linkPreviewError.textContent = error.message;
        linkPreviewError.hidden = false;
      }
    });
  });
  if (linkPreviewDialog) {
    linkPreviewDialog.querySelectorAll('[data-link-preview-close]').forEach((button) => {
      button.addEventListener('click', () => linkPreviewDialog.close());
    });
    linkPreviewDialog.addEventListener('click', (event) => {
      if (event.target === linkPreviewDialog) linkPreviewDialog.close();
    });
    linkPreviewImage?.addEventListener('load', () => {
      linkPreviewLoading.hidden = true;
      linkPreviewError.hidden = true;
      linkPreviewImage.hidden = false;
    });
    linkPreviewImage?.addEventListener('error', () => {
      linkPreviewLoading.hidden = true;
      linkPreviewImage.hidden = true;
      linkPreviewError.hidden = false;
    });
    linkPreviewDialog.addEventListener('close', () => {
      linkPreviewController?.abort();
      if (linkPreviewObjectUrl) URL.revokeObjectURL(linkPreviewObjectUrl);
      linkPreviewObjectUrl = undefined;
      linkPreviewImage?.removeAttribute('src');
      if (linkPreviewImage) linkPreviewImage.hidden = true;
      if (linkPreviewLoading) linkPreviewLoading.hidden = false;
      if (linkPreviewError) linkPreviewError.hidden = true;
      if (linkPreviewStatus) linkPreviewStatus.hidden = true;
      if (linkPreviewHost) linkPreviewHost.textContent = '';
      if (linkPreviewUrl) linkPreviewUrl.textContent = '';
      if (linkPreviewContinue) {
        linkPreviewContinue.removeAttribute('href');
        linkPreviewContinue.setAttribute('aria-disabled', 'true');
      }
    });
  }

  const contactDialog = document.querySelector('[data-contact-dialog]');
  if (contactDialog) {
    const openContactDialog = () => {
      if (typeof contactDialog.showModal === 'function' && !contactDialog.open) {
        contactDialog.showModal();
      }
    };
    document.querySelector('[data-contact-dialog-open]')?.addEventListener('click', openContactDialog);
    contactDialog.querySelector('[data-contact-dialog-close]')?.addEventListener('click', () => contactDialog.close());
    contactDialog.addEventListener('click', (event) => {
      if (event.target === contactDialog) contactDialog.close();
    });
    if (window.location.hash === '#report-contact') openContactDialog();
  }

  async function initializePlaces() {
    const slot = document.querySelector('[data-place-autocomplete]');
    if (!slot || !window.shopAlertPlacesEnabled) return;
    try {
      const { Place, PlaceAutocompleteElement } = await google.maps.importLibrary('places');
      const autocomplete = new PlaceAutocompleteElement({
        requestedLanguage: slot.dataset.placeLanguage || 'en-US',
        requestedRegion: slot.dataset.placeRegion || 'us',
      });
      autocomplete.setAttribute('aria-label', i18n.placeLabel || 'Search for a shop with Google Places');
      slot.replaceChildren(autocomplete);
      autocomplete.addEventListener('gmp-select', async ({ placePrediction }) => {
        const place = placePrediction.toPlace();
        await place.fetchFields({ fields: ['displayName', 'formattedAddress', 'location'] });
        const name = document.querySelector('[data-shop-name]');
        const address = document.querySelector('[data-shop-address]');
        const lat = document.querySelector('[data-place-lat]');
        const lng = document.querySelector('[data-place-lng]');
        const id = document.querySelector('[data-place-id]');
        const addressEnUs = document.querySelector('[data-place-address-en-us]');
        const addressZhTw = document.querySelector('[data-place-address-zh-tw]');
        const activeLanguage = slot.dataset.placeLanguage || 'en-US';
        const activeAddress = place.formattedAddress || '';
        let englishAddress = activeLanguage === 'en-US' ? activeAddress : '';
        let traditionalChineseAddress = activeLanguage === 'zh-TW' ? activeAddress : '';

        try {
          const alternateLanguage = activeLanguage === 'zh-TW' ? 'en-US' : 'zh-TW';
          const alternateRegion = alternateLanguage === 'zh-TW' ? 'tw' : 'us';
          const alternatePlace = new Place({
            id: place.id,
            requestedLanguage: alternateLanguage,
            requestedRegion: alternateRegion,
          });
          await alternatePlace.fetchFields({ fields: ['formattedAddress'] });
          if (alternateLanguage === 'zh-TW') {
            traditionalChineseAddress = alternatePlace.formattedAddress || '';
          } else {
            englishAddress = alternatePlace.formattedAddress || '';
          }
        } catch (error) {
          console.warn('Could not fetch the alternate localized address', error);
        }

        if (name) name.value = place.displayName || '';
        if (address) address.value = activeAddress;
        if (lat && place.location) lat.value = place.location.lat();
        if (lng && place.location) lng.value = place.location.lng();
        if (id) id.value = place.id || '';
        if (addressEnUs) addressEnUs.value = englishAddress;
        if (addressZhTw) addressZhTw.value = traditionalChineseAddress;
        document.dispatchEvent(new CustomEvent('shopalert:place-selected'));
      });
    } catch (error) {
      const message = document.createElement('span');
      message.className = 'loading-line';
      message.textContent = i18n.placeFailed || 'Google Places could not load. Please enter the shop manually.';
      slot.replaceChildren(message);
      console.warn('Google Places initialization failed', error);
    }
  }
  initializePlaces();
})();
