/**
 * Bootstrap 5 Sidebar Navigation Active State Management
 * File: sidebar-nav.js
 * 
 * This script manages the active state of sidebar navigation items
 * based on the current URL path. It handles both top-level links
 * and nested submenu items with Bootstrap 5 collapse functionality.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Ensure modals are appended to body for proper z-index stacking
    $(function() {
        $('.modal').appendTo('body');
    });
    
    // Initialize MetisMenu
    $('#sidebar-menu').metisMenu();
    
    // Get current URL path
    const currentPath = window.location.pathname;
    
    // Find all sidebar menu items
    const menuItems = document.querySelectorAll('.vertical-nav-menu a');
    
    // Close all submenus first
    const submenus = document.querySelectorAll('.vertical-nav-menu ul.mm-collapse');
    submenus.forEach(function(submenu) {
        submenu.classList.remove('mm-show');
    });
    
    // Remove active classes from all items
    menuItems.forEach(function(item) {
        item.classList.remove('mm-active');
        if (item.parentElement) {
            item.parentElement.classList.remove('mm-active');
        }
    });
    
    // Loop through each menu item to find and activate the current one
    menuItems.forEach(function(item) {
        // Get the href attribute
        const itemHref = item.getAttribute('href');
        
        // Skip if no href or if it's a dropdown toggle (#)
        if (!itemHref || itemHref === '#') return;
        
        // Convert relative URLs to absolute for comparison
        const itemPath = itemHref.replace(/^https?:\/\/[^\/]+/, '');
        
        // Check if current path matches or starts with this menu item's path
        // Avoid matching root path with everything
        if ((currentPath === itemPath) || 
            (itemPath !== '/' && currentPath.startsWith(itemPath))) {
            
            // Add active class to the link
            item.classList.add('mm-active');
            
            // If this is a submenu item, expand the parent menu
            const parentLi = item.closest('li');
            if (parentLi) {
                // Add active class to parent li
                parentLi.classList.add('mm-active');
                
                // Find parent ul and add show class
                const parentUl = parentLi.closest('ul');
                if (parentUl && parentUl.classList.contains('mm-collapse')) {
                    parentUl.classList.add('mm-show');
                    
                    // Add active class to parent li of this ul
                    const grandparentLi = parentUl.parentElement;
                    if (grandparentLi) {
                        grandparentLi.classList.add('mm-active');
                        
                        // Add active class to the direct link inside the grandparent li
                        const grandparentLink = grandparentLi.querySelector('a');
                        if (grandparentLink) {
                            grandparentLink.classList.add('mm-active');
                        }
                    }
                }
            }
        }
    });
    
    // Event handler for menu toggles to properly collapse other menus
    const menuToggleLinks = document.querySelectorAll('.vertical-nav-menu > li > a[href="#"]');
    menuToggleLinks.forEach(function(link) {
        link.addEventListener('click', function(e) {
            // If this menu is not active, close all other open menus
            if (!this.classList.contains('mm-active')) {
                const openSubmenus = document.querySelectorAll('.vertical-nav-menu > li > ul.mm-show');
                openSubmenus.forEach(function(submenu) {
                    if (submenu.parentElement !== link.parentElement) {
                        submenu.classList.remove('mm-show');
                        const parentLink = submenu.parentElement.querySelector('a');
                        if (parentLink) {
                            parentLink.classList.remove('mm-active');
                        }
                        submenu.parentElement.classList.remove('mm-active');
                    }
                });
            }
        });
    });
    
});

