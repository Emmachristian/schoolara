// theme-settings.js - Complete theme management system for Schoolara

(function() {
    'use strict';
    
    console.log('Theme settings script loading...');
    
    // ==========================================
    // UTILITY FUNCTIONS
    // ==========================================
    
    // Get CSRF token for Django
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Save theme preference to server via AJAX
    function saveThemePreference(setting, value) {
        fetch('/save-theme-preference/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                setting: setting,
                value: value
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('✓ Theme saved:', setting, '=', value);
                
                // Show success notification if toastr is available
                if (typeof toastr !== 'undefined') {
                    toastr.success('Theme updated successfully', 'Settings Saved');
                }
            } else {
                console.error('Failed to save theme:', data.error);
                
                // Show error notification
                if (typeof toastr !== 'undefined') {
                    toastr.error(data.error || 'Failed to save theme', 'Error');
                }
            }
        })
        .catch(error => {
            console.error('Error saving theme:', error);
            
            // Show network error
            if (typeof toastr !== 'undefined') {
                toastr.error('Network error. Please check your connection.', 'Error');
            }
        });
    }

    // Wait for DOM to be ready
    function initThemeSettings() {
        console.log('Initializing theme settings...');
        
        // ==========================================
        // THEME SETTINGS PANEL TOGGLE
        // ==========================================
        const themeSettingsBtn = document.getElementById('TooltipDemo');
        const themeSettings = document.querySelector('.ui-theme-settings');
        
        console.log('Settings button:', themeSettingsBtn);
        console.log('Settings panel:', themeSettings);
        
        if (themeSettingsBtn && themeSettings) {
            console.log('Adding click handler to settings button');
            
            themeSettingsBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                console.log('Settings button clicked!');
                
                // Check class state BEFORE toggling
                const isOpen = themeSettings.classList.contains('settings-open');
                console.log('Panel is currently:', isOpen ? 'open' : 'closed');
                
                if (isOpen) {
                    themeSettings.classList.remove('settings-open');
                    // Reset inline styles when closing
                    themeSettings.style.transform = '';
                    themeSettings.style.right = '';
                    console.log('Closing panel');
                } else {
                    themeSettings.classList.add('settings-open');
                    // Force visibility if CSS isn't working
                    themeSettings.style.transform = 'translate(0)';
                    themeSettings.style.right = '0';
                    console.log('Opening panel');
                }
                
                // Verify the class was actually added
                setTimeout(() => {
                    console.log('After toggle, panel has settings-open?', themeSettings.classList.contains('settings-open'));
                }, 10);
                
                return false;
            });
            
            // Close when clicking outside
            document.addEventListener('click', function(e) {
                if (!themeSettings.contains(e.target) && !themeSettingsBtn.contains(e.target)) {
                    if (themeSettings.classList.contains('settings-open')) {
                        console.log('Clicking outside - closing panel');
                        themeSettings.classList.remove('settings-open');
                        // Reset inline styles when closing
                        themeSettings.style.transform = '';
                        themeSettings.style.right = '';
                    }
                }
            });
            
            console.log('✓ Settings panel toggle initialized');
        } else {
            console.error('❌ Settings button or panel not found!');
        }

        // ==========================================
        // FIXED LAYOUT TOGGLES (Header, Sidebar, Footer)
        // ==========================================
        const switchContainers = document.querySelectorAll('.switch-container-class');
        console.log('Found', switchContainers.length, 'layout toggle switches');
        
        switchContainers.forEach(container => {
            const checkbox = container.querySelector('input[type="checkbox"]');
            const switchAnimate = container.querySelector('.switch-animate');
            const targetClass = container.getAttribute('data-class');
            
            if (checkbox && switchAnimate) {
                // Set initial state based on body classes
                const bodyHasClass = document.body.classList.contains(targetClass);
                checkbox.checked = bodyHasClass;
                if (bodyHasClass) {
                    switchAnimate.classList.remove('switch-off');
                    switchAnimate.classList.add('switch-on');
                } else {
                    switchAnimate.classList.remove('switch-on');
                    switchAnimate.classList.add('switch-off');
                }
                
                switchAnimate.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    const isChecked = checkbox.checked;
                    const newState = !isChecked;
                    
                    checkbox.checked = newState;
                    
                    // Update visual state
                    if (newState) {
                        switchAnimate.classList.remove('switch-off');
                        switchAnimate.classList.add('switch-on');
                        document.body.classList.add(targetClass);
                    } else {
                        switchAnimate.classList.remove('switch-on');
                        switchAnimate.classList.add('switch-off');
                        document.body.classList.remove(targetClass);
                    }
                    
                    // Save to server
                    saveThemePreference(targetClass.replace('-', '_'), newState.toString());
                });
            }
        });

        // ==========================================
        // HEADER COLOR SCHEME
        // ==========================================
        const headerSwatches = document.querySelectorAll('.switch-header-cs-class');
        const appHeader = document.querySelector('.app-header');
        console.log('Found', headerSwatches.length, 'header color swatches');
        
        // Mark currently active header color on load
        const savedHeaderClass = window.THEME_CONFIG?.headerClass || '';
        console.log('Saved header class:', savedHeaderClass);
        headerSwatches.forEach(swatch => {
            const swatchClass = swatch.getAttribute('data-class') || '';
            // Exact match only
            if (swatchClass === savedHeaderClass) {
                swatch.classList.add('active');
                console.log('Marked header swatch as active:', swatchClass);
            }
        });
        
        headerSwatches.forEach(swatch => {
            swatch.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const newClass = this.getAttribute('data-class');
                
                // Remove active state from all swatches
                headerSwatches.forEach(s => s.classList.remove('active'));
                
                // Add active state to clicked swatch
                this.classList.add('active');
                
                // Remove all existing header classes
                headerSwatches.forEach(s => {
                    const cls = s.getAttribute('data-class');
                    if (cls) {
                        cls.split(' ').forEach(c => appHeader.classList.remove(c));
                    }
                });
                
                // Add new header class
                if (newClass) {
                    newClass.split(' ').forEach(cls => appHeader.classList.add(cls));
                    saveThemePreference('header_class', newClass);
                } else {
                    // Restore default clicked
                    saveThemePreference('header_class', '');
                }
            });
        });

        // ==========================================
        // SIDEBAR COLOR SCHEME
        // ==========================================
        const sidebarSwatches = document.querySelectorAll('.switch-sidebar-cs-class');
        const appSidebar = document.querySelector('.app-sidebar');
        console.log('Found', sidebarSwatches.length, 'sidebar color swatches');
        
        // Mark currently active sidebar color on load
        const savedSidebarClass = window.THEME_CONFIG?.sidebarClass || '';
        console.log('Saved sidebar class:', savedSidebarClass);
        sidebarSwatches.forEach(swatch => {
            const swatchClass = swatch.getAttribute('data-class') || '';
            // Exact match only
            if (swatchClass === savedSidebarClass) {
                swatch.classList.add('active');
                console.log('Marked sidebar swatch as active:', swatchClass);
            }
        });
        
        sidebarSwatches.forEach(swatch => {
            swatch.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const newClass = this.getAttribute('data-class');
                
                // Remove active state from all swatches
                sidebarSwatches.forEach(s => s.classList.remove('active'));
                
                // Add active state to clicked swatch
                this.classList.add('active');
                
                // Remove all existing sidebar classes
                sidebarSwatches.forEach(s => {
                    const cls = s.getAttribute('data-class');
                    if (cls) {
                        cls.split(' ').forEach(c => appSidebar.classList.remove(c));
                    }
                });
                
                // Add new sidebar class
                if (newClass) {
                    newClass.split(' ').forEach(cls => appSidebar.classList.add(cls));
                    saveThemePreference('sidebar_class', newClass);
                } else {
                    // Restore default clicked
                    saveThemePreference('sidebar_class', '');
                }
            });
        });

        // ==========================================
        // MAIN CONTENT OPTIONS (Page Tabs & Theme)
        // ==========================================
        const themeButtons = document.querySelectorAll('.switch-theme-class');
        console.log('Found', themeButtons.length, 'theme buttons');
        
        themeButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const targetClass = this.getAttribute('data-class');
                
                // Handle page tabs style
                if (targetClass.includes('body-tabs')) {
                    document.body.classList.remove('body-tabs-shadow', 'body-tabs-line');
                    document.body.classList.add(targetClass);
                    
                    // Update button states
                    themeButtons.forEach(btn => {
                        if (btn.getAttribute('data-class').includes('body-tabs')) {
                            btn.classList.remove('active');
                        }
                    });
                    this.classList.add('active');
                    
                    saveThemePreference('page_tabs_style', targetClass);
                } 
                // Handle theme color
                else if (targetClass.includes('app-theme')) {
                    document.body.classList.remove('app-theme-white', 'app-theme-gray');
                    document.body.classList.add(targetClass);
                    
                    // Update button states
                    themeButtons.forEach(btn => {
                        if (btn.getAttribute('data-class').includes('app-theme')) {
                            btn.classList.remove('active');
                        }
                    });
                    this.classList.add('active');
                    
                    saveThemePreference('theme_color', targetClass);
                }
            });
        });

        // Main content restore defaults
        const restoreMainBtn = document.getElementById('restoreMainDefaults');
        if (restoreMainBtn) {
            restoreMainBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                // Reset button states
                themeButtons.forEach(btn => {
                    btn.classList.remove('active');
                    const dataClass = btn.getAttribute('data-class');
                    if (dataClass === 'body-tabs-shadow' || dataClass === 'app-theme-white') {
                        btn.classList.add('active');
                    }
                });
                
                // Apply defaults
                document.body.classList.remove('body-tabs-line', 'app-theme-gray');
                document.body.classList.add('body-tabs-shadow', 'app-theme-white');
                
                // Save to server
                saveThemePreference('page_tabs_style', 'body-tabs-shadow');
                saveThemePreference('theme_color', 'app-theme-white');
            });
        }

        console.log('✓ Theme settings system fully initialized');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initThemeSettings);
    } else {
        initThemeSettings();
    }
    
})();