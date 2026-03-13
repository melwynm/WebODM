(function () {
    function getCsrfToken() {
        var cookies = document.cookie ? document.cookie.split(';') : [];
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === 'csrftoken=') {
                return decodeURIComponent(cookie.substring(10));
            }
        }
        return '';
    }

    function maskToken(token) {
        var visibleChars = 8;
        if (!token) return '';
        var suffix = token.slice(-visibleChars);
        return '\u2022'.repeat(Math.max(token.length - suffix.length, 0)) + suffix;
    }

    function setStatus(manager, message, isError) {
        var status = manager.querySelector('[data-api-token-status]');
        if (!status) return;
        status.textContent = message || '';
        status.classList.toggle('is-error', !!isError);
    }

    function setBusy(manager, busy) {
        var buttons = manager.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].disabled = busy;
        }
    }

    function updateInput(manager) {
        var input = manager.querySelector('[data-api-token-input]');
        var isVisible = manager.dataset.visible === 'true';
        var fullToken = manager._apiToken || '';
        if (!input) return;

        if (isVisible && fullToken) {
            input.value = fullToken;
        } else {
            input.value = manager.dataset.maskedToken || '';
        }
    }

    function setVisible(manager, visible) {
        var toggle = manager.querySelector('[data-api-token-toggle]');
        manager.dataset.visible = visible ? 'true' : 'false';
        updateInput(manager);
        if (toggle) {
            toggle.textContent = visible ? manager.dataset.hideLabel : manager.dataset.showLabel;
        }
    }

    async function parseResponse(response, fallbackMessage) {
        var data = null;
        try {
            data = await response.json();
        } catch (error) {
            data = null;
        }

        if (!response.ok) {
            throw new Error((data && (data.detail || data.api_key)) || fallbackMessage);
        }

        return data || {};
    }

    async function fetchToken(manager) {
        if (manager._apiToken) {
            return manager._apiToken;
        }

        setBusy(manager, true);
        try {
            var response = await fetch(manager.dataset.fetchUrl, {
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json'
                }
            });
            var data = await parseResponse(response, manager.dataset.loadError);
            manager._apiToken = data.api_key || '';
            manager.dataset.maskedToken = maskToken(manager._apiToken);
            updateInput(manager);
            return manager._apiToken;
        } catch (error) {
            setStatus(manager, error.message || manager.dataset.loadError, true);
            throw error;
        } finally {
            setBusy(manager, false);
        }
    }

    async function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            return;
        }

        var textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', 'readonly');
        textarea.style.position = 'absolute';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }

    async function handleToggle(manager) {
        if (manager.dataset.visible === 'true') {
            setVisible(manager, false);
            return;
        }

        await fetchToken(manager);
        setVisible(manager, true);
        setStatus(manager, '', false);
    }

    async function handleCopy(manager) {
        try {
            var token = await fetchToken(manager);
            await copyText(token);
            setStatus(manager, manager.dataset.copySuccess, false);
        } catch (error) {
            setStatus(manager, manager.dataset.copyError, true);
        }
    }

    async function handleRegenerate(manager) {
        if (!window.confirm(manager.dataset.confirmMessage)) {
            return;
        }

        setBusy(manager, true);
        try {
            var response = await fetch(manager.dataset.regenerateUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            var data = await parseResponse(response, manager.dataset.regenerateError);
            manager._apiToken = data.api_key || '';
            manager.dataset.maskedToken = maskToken(manager._apiToken);
            setVisible(manager, true);
            setStatus(manager, manager.dataset.regenerateSuccess, false);
        } catch (error) {
            setStatus(manager, error.message || manager.dataset.regenerateError, true);
        } finally {
            setBusy(manager, false);
        }
    }

    function initManager(manager) {
        if (manager.dataset.apiTokenReady === 'true') {
            return;
        }

        manager.dataset.apiTokenReady = 'true';
        setVisible(manager, false);

        var toggle = manager.querySelector('[data-api-token-toggle]');
        var copy = manager.querySelector('[data-api-token-copy]');
        var regenerate = manager.querySelector('[data-api-token-regenerate]');

        if (toggle) {
            toggle.addEventListener('click', function () {
                handleToggle(manager).catch(function () {});
            });
        }

        if (copy) {
            copy.addEventListener('click', function () {
                handleCopy(manager).catch(function () {});
            });
        }

        if (regenerate) {
            regenerate.addEventListener('click', function () {
                handleRegenerate(manager).catch(function () {});
            });
        }
    }

    function init() {
        var managers = document.querySelectorAll('[data-api-token-manager]');
        for (var i = 0; i < managers.length; i++) {
            initManager(managers[i]);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
