function setColorScheme(t) {
    const classes = document.documentElement.classList;
    classes.remove('light', 'dark');

    const buttons = document.querySelectorAll('.theme-toggle button');
    for(const button of buttons) {
        button.classList.toggle(
            'active',
            (t === 'light' && button.classList.contains('fa-sun-o'))
            || (t === 'dark' && button.classList.contains('fa-moon-o'))
            || (t !== 'light' && t !== 'dark' && button.classList.contains('fa-ban'))
        );
    }

    switch (t) {
    case 'light': case 'dark':
        classes.add(t);
        window.localStorage.setItem('color-scheme', t);
        break;
    default:
        window.localStorage.removeItem('color-scheme');
    }
}

window.addEventListener("click", (e) => {
    const target = e.target;
    if (target.matches(".btn-group.theme-toggle button")) {
        setColorScheme(
            target.classList.contains('fa-sun-o') ? 'light' :
                target.classList.contains('fa-moon-o') ? 'dark' :
                    null
        );
    }
});

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", (e) => {
        setColorScheme(window.localStorage.getItem('color-scheme'));
    });
} else {
    setColorScheme(window.localStorage.getItem('color-scheme'));
}
