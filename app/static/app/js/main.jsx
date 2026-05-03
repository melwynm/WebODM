import '../css/main.scss';
import './django/csrf';
import ReactDOM from 'react-dom';
import React from 'react';
import $ from 'jquery';
import PluginsAPI from './classes/plugins/API';
import { setLocale } from './translations/functions';

// Main is always executed first in the page

// Silence annoying React deprecation notice of useful functionality
const originalError = console.error;
console.error = function(...args) {
  let message = args[0];
  if (typeof message === 'string' && message.indexOf('Warning: A future version of React will block javascript:') !== -1) {
    return;
  }
  originalError.apply(console, args);
};

// We share some objects to avoid having to include them
// as a dependency in each component (adds too much space overhead)
window.ReactDOM = ReactDOM;
window.React = React;

// Expose set locale function globally
window.setLocale = setLocale;

function applyShellTheme(theme){
    const nextTheme = theme === 'light' ? 'light' : 'dark';
    document.body.setAttribute('data-shell-theme', nextTheme);

    const toggle = document.querySelector('[data-shell-theme-toggle]');
    if (!toggle) return;

    const icon = toggle.querySelector('.shell-theme-toggle__icon');
    const label = toggle.querySelector('.shell-theme-toggle__label');
    if (icon){
        icon.className = `fa fa-${nextTheme === 'light' ? 'sun' : 'moon'} fa-fw shell-theme-toggle__icon`;
    }
    if (label){
        label.textContent = nextTheme === 'light' ? 'Light' : 'Dark';
    }
    toggle.setAttribute('aria-pressed', nextTheme === 'light' ? 'true' : 'false');
}

$(function(){
    let storedTheme = 'dark';
    try {
        storedTheme = localStorage.getItem('webodm-shell-theme') || 'dark';
    } catch (e) {
        storedTheme = 'dark';
    }
    applyShellTheme(storedTheme);

    $(document).on('click', '[data-shell-theme-toggle]', function(){
        const currentTheme = document.body.getAttribute('data-shell-theme') === 'light' ? 'light' : 'dark';
        const nextTheme = currentTheme === 'light' ? 'dark' : 'light';
        try {
            localStorage.setItem('webodm-shell-theme', nextTheme);
        } catch (e) {
            // Ignore private browsing/storage failures.
        }
        applyShellTheme(nextTheme);
    });

    PluginsAPI.App.triggerReady();
});
