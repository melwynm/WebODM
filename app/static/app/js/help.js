(function () {
    'use strict';

    function initializeHelpSearch() {
        var input = document.getElementById('help-search');
        var clearButton = document.getElementById('help-clear');
        var status = document.getElementById('help-search-status');
        var emptyState = document.getElementById('help-empty');
        var cards = Array.prototype.slice.call(document.querySelectorAll('[data-help-item]'));
        var resetButtons = document.querySelectorAll('[data-help-reset]');

        if (!input || !status || !cards.length) return;

        function normalize(value) {
            return (value || '').toLowerCase().replace(/\s+/g, ' ').trim();
        }

        function searchableText(card) {
            return normalize((card.getAttribute('data-help-search') || '') + ' ' + card.textContent);
        }

        var index = cards.map(function (card) {
            return {card: card, text: searchableText(card)};
        });

        function updateStatus(visible) {
            if (visible === 0) {
                status.textContent = status.getAttribute('data-no-results');
            } else {
                var label = visible === 1
                    ? status.getAttribute('data-result-singular')
                    : status.getAttribute('data-result-plural');
                status.textContent = visible + ' ' + label;
            }
        }

        function filterGuides() {
            var query = normalize(input.value);
            var words = query ? query.split(' ') : [];
            var visible = 0;

            index.forEach(function (entry) {
                var matches = words.every(function (word) {
                    return entry.text.indexOf(word) !== -1;
                });
                entry.card.hidden = !matches;
                if (matches) visible += 1;
            });

            if (clearButton) clearButton.hidden = !query;
            if (emptyState) emptyState.hidden = visible !== 0;
            updateStatus(visible);
        }

        function resetSearch() {
            input.value = '';
            filterGuides();
            input.focus();
        }

        input.addEventListener('input', filterGuides);
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && input.value) resetSearch();
        });
        if (clearButton) clearButton.addEventListener('click', resetSearch);
        Array.prototype.forEach.call(resetButtons, function (button) {
            button.addEventListener('click', resetSearch);
        });

        filterGuides();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeHelpSearch);
    } else {
        initializeHelpSearch();
    }
}());
