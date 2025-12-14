# core/context_processors.py

from accounts.models import School

def active_school(request):
    """
    Adds the current active school (or subscription info) to all templates.
    """
    school = None
    if request.user.is_authenticated:
        profile = getattr(request.user, 'userprofile', None)
        if profile:
            school = profile.school
    return {'active_school': school}


def user_context(request):
    """
    Provides user-specific context including profile and theme preferences.
    """
    context = {}
    if request.user.is_authenticated:
        profile = getattr(request.user, 'userprofile', None)
        
        # Basic user info
        context['user_first_name'] = request.user.first_name
        context['user_last_name'] = request.user.last_name
        context['user_email'] = request.user.email
        
        # Profile-specific info
        if profile:
            context['user_role'] = profile.role
            context['user_profile_pic'] = profile.photo
            context['user_school'] = profile.school
            
            # Theme preferences
            context['fixed_header'] = profile.fixed_header
            context['fixed_sidebar'] = profile.fixed_sidebar
            context['fixed_footer'] = profile.fixed_footer
            context['header_class'] = profile.header_class
            context['sidebar_class'] = profile.sidebar_class
            context['page_tabs_style'] = profile.page_tabs_style
            context['theme_color'] = profile.theme_color
        
    return context


def theme_colors(request):
    """
    Provides comprehensive theme color configuration for templates.
    This includes color schemes, text color mappings, and theme options.
    """
    
    # Define color schemes with their properties
    COLOR_SCHEMES = {
        # Basic Bootstrap colors
        'primary': {'label': 'Primary Blue', 'text': 'light'},
        'secondary': {'label': 'Secondary Gray', 'text': 'light'},
        'success': {'label': 'Success Green', 'text': 'light'},
        'info': {'label': 'Info Cyan', 'text': 'light'},
        'warning': {'label': 'Warning Yellow', 'text': 'dark'},
        'danger': {'label': 'Danger Red', 'text': 'light'},
        'light': {'label': 'Light', 'text': 'dark'},
        'dark': {'label': 'Dark', 'text': 'light'},
        'focus': {'label': 'Focus Purple', 'text': 'light'},
        'alternate': {'label': 'Alternate', 'text': 'light'},
        
        # Gradient/Premium colors
        'vicious-stance': {'label': 'Vicious Stance', 'text': 'light'},
        'midnight-bloom': {'label': 'Midnight Bloom', 'text': 'light'},
        'night-sky': {'label': 'Night Sky', 'text': 'light'},
        'slick-carbon': {'label': 'Slick Carbon', 'text': 'light'},
        'asteroid': {'label': 'Asteroid', 'text': 'light'},
        'royal': {'label': 'Royal', 'text': 'light'},
        'warm-flame': {'label': 'Warm Flame', 'text': 'dark'},
        'night-fade': {'label': 'Night Fade', 'text': 'dark'},
        'sunny-morning': {'label': 'Sunny Morning', 'text': 'dark'},
        'tempting-azure': {'label': 'Tempting Azure', 'text': 'dark'},
        'amy-crisp': {'label': 'Amy Crisp', 'text': 'dark'},
        'heavy-rain': {'label': 'Heavy Rain', 'text': 'dark'},
        'mean-fruit': {'label': 'Mean Fruit', 'text': 'dark'},
        'malibu-beach': {'label': 'Malibu Beach', 'text': 'light'},
        'deep-blue': {'label': 'Deep Blue', 'text': 'dark'},
        'ripe-malin': {'label': 'Ripe Malin', 'text': 'light'},
        'arielle-smile': {'label': 'Arielle Smile', 'text': 'light'},
        'plum-plate': {'label': 'Plum Plate', 'text': 'light'},
        'happy-fisher': {'label': 'Happy Fisher', 'text': 'dark'},
        'happy-itmeo': {'label': 'Happy Itmeo', 'text': 'light'},
        'mixed-hopes': {'label': 'Mixed Hopes', 'text': 'light'},
        'strong-bliss': {'label': 'Strong Bliss', 'text': 'light'},
        'grow-early': {'label': 'Grow Early', 'text': 'light'},
        'love-kiss': {'label': 'Love Kiss', 'text': 'light'},
        'premium-dark': {'label': 'Premium Dark', 'text': 'light'},
        'happy-green': {'label': 'Happy Green', 'text': 'light'},
    }
    
    # Separate basic and gradient colors for template organization
    basic_color_keys = [
        'primary', 'secondary', 'success', 'info', 
        'warning', 'danger', 'light', 'dark', 'focus', 'alternate'
    ]
    
    gradient_color_keys = [k for k in COLOR_SCHEMES.keys() if k not in basic_color_keys]
    
    # Build color lists with full information
    basic_colors = [
        {
            'key': key,
            'label': COLOR_SCHEMES[key]['label'],
            'text_class': COLOR_SCHEMES[key]['text'],
            'bg_class': f'bg-{key}',
            'full_class': f"bg-{key} header-text-{COLOR_SCHEMES[key]['text']}"
        }
        for key in basic_color_keys
    ]
    
    gradient_colors = [
        {
            'key': key,
            'label': COLOR_SCHEMES[key]['label'],
            'text_class': COLOR_SCHEMES[key]['text'],
            'bg_class': f'bg-{key}',
            'full_class': f"bg-{key} header-text-{COLOR_SCHEMES[key]['text']}"
        }
        for key in gradient_color_keys
    ]
    
    # Theme options
    theme_options = [
        {
            'value': 'app-theme-white',
            'label': 'White Theme',
            'class': 'light',
            'active': request.user.is_authenticated and 
                     getattr(getattr(request.user, 'userprofile', None), 'theme_color', 'app-theme-white') == 'app-theme-white'
        },
        {
            'value': 'app-theme-gray',
            'label': 'Gray Theme',
            'class': 'light',
            'active': request.user.is_authenticated and 
                     getattr(getattr(request.user, 'userprofile', None), 'theme_color', '') == 'app-theme-gray'
        },
    ]
    
    # Tab style options
    tab_style_options = [
        {
            'value': 'body-tabs-shadow',
            'label': 'Shadow',
            'active': request.user.is_authenticated and 
                     getattr(getattr(request.user, 'userprofile', None), 'page_tabs_style', 'body-tabs-shadow') == 'body-tabs-shadow'
        },
        {
            'value': 'body-tabs-line',
            'label': 'Line',
            'active': request.user.is_authenticated and 
                     getattr(getattr(request.user, 'userprofile', None), 'page_tabs_style', '') == 'body-tabs-line'
        },
    ]
    
    # Helper function to get text class for a color
    def get_text_class(color_key):
        return COLOR_SCHEMES.get(color_key, {}).get('text', 'light')
    
    return {
        'color_schemes': COLOR_SCHEMES,
        'basic_colors': basic_colors,
        'gradient_colors': gradient_colors,
        'all_colors': basic_colors + gradient_colors,
        'theme_options': theme_options,
        'tab_style_options': tab_style_options,
        'get_text_class': get_text_class,  # Helper for templates
    }