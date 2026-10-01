// Presentation only: no API calls, authentication changes, or business state.
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('student-sidebar');
  const toggle = document.querySelector('.student-sidebar-toggle');
  const backdrop = document.querySelector('.student-sidebar-backdrop');
  const closeButton = document.querySelector('.student-sidebar-close');
  if (!sidebar || !toggle || !backdrop || !closeButton) return;
  const mobile = window.matchMedia('(max-width: 768px)');
  const hoverAvailable = window.matchMedia('(hover: hover) and (pointer: fine)');
  let desktopPinned = document.body.classList.contains('sidebar-expanded');
  let sidebarHovered = false;
  let keyboardFocus = false;
  const tooltip = document.createElement('div');
  tooltip.className = 'student-nav-tooltip';
  tooltip.hidden = true;
  document.body.appendChild(tooltip);

  function syncNavigation() {
    const open = mobile.matches && document.body.classList.contains('sidebar-open');
    const expanded = !mobile.matches && (desktopPinned || sidebarHovered || keyboardFocus);
    document.body.classList.toggle('sidebar-expanded', expanded);
    toggle.setAttribute('aria-expanded', String(open || expanded));
    toggle.setAttribute('aria-label', mobile.matches ? (open ? 'Close navigation' : 'Open navigation') : (desktopPinned ? 'Collapse navigation' : (expanded ? 'Keep navigation expanded' : 'Expand navigation')));
    sidebar.inert = mobile.matches && !open;
    backdrop.hidden = !open;
    tooltip.hidden = true;
  }
  function closeDrawer(restoreFocus = true) {
    document.body.classList.remove('sidebar-open');
    syncNavigation();
    if (restoreFocus) toggle.focus();
  }
  toggle.addEventListener('click', () => {
    if (mobile.matches) document.body.classList.toggle('sidebar-open');
    else desktopPinned = !desktopPinned;
    syncNavigation();
    if (mobile.matches && document.body.classList.contains('sidebar-open')) closeButton.focus();
  });
  sidebar.addEventListener('pointerenter', event => {
    if (mobile.matches || !hoverAvailable.matches || event.pointerType !== 'mouse') return;
    sidebarHovered = true;
    syncNavigation();
  });
  sidebar.addEventListener('pointerleave', () => {
    sidebarHovered = false;
    syncNavigation();
  });
  sidebar.addEventListener('focusin', event => {
    keyboardFocus = event.target.matches(':focus-visible');
    syncNavigation();
  });
  sidebar.addEventListener('focusout', event => {
    if (sidebar.contains(event.relatedTarget)) return;
    keyboardFocus = false;
    syncNavigation();
  });
  closeButton.addEventListener('click', () => closeDrawer());
  backdrop.addEventListener('click', () => closeDrawer());
  sidebar.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    if (mobile.matches) closeDrawer(false);
  }));
  document.addEventListener('keydown', event => {
    if (!mobile.matches || !document.body.classList.contains('sidebar-open')) return;
    if (event.key === 'Escape') closeDrawer();
    if (event.key === 'Tab') {
      const items = sidebar.querySelectorAll('a, button');
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  mobile.addEventListener('change', () => {
    desktopPinned = sidebarHovered = keyboardFocus = false;
    document.body.classList.remove('sidebar-open', 'sidebar-expanded');
    syncNavigation();
  });
  hoverAvailable.addEventListener('change', () => {
    sidebarHovered = false;
    syncNavigation();
  });
  window.addEventListener('blur', () => {
    sidebarHovered = false;
    syncNavigation();
  });
  sidebar.querySelectorAll('[data-tooltip]').forEach(item => {
    const show = () => {
      if (mobile.matches || document.body.classList.contains('sidebar-expanded')) return;
      const bounds = item.getBoundingClientRect();
      tooltip.textContent = item.dataset.tooltip;
      tooltip.style.left = `${sidebar.getBoundingClientRect().right + 10}px`;
      tooltip.style.top = `${bounds.top + (bounds.height - 32) / 2}px`;
      tooltip.hidden = false;
    };
    item.addEventListener('mouseenter', show);
    item.addEventListener('focus', show);
    item.addEventListener('mouseleave', () => { tooltip.hidden = true; });
    item.addEventListener('blur', () => { tooltip.hidden = true; });
  });
  sidebar.addEventListener('scroll', () => { tooltip.hidden = true; }, true);
  window.addEventListener('resize', () => { tooltip.hidden = true; });
  // The advisor's conversation history remains a separate, existing control.
  // Set its initial mobile presentation and reflect the existing collapsed class.
  const history = document.querySelector('.student-advisor-page #sidebar');
  const historyToggle = document.querySelector('.student-advisor-page #sidebar-toggle');
  if (history && historyToggle) {
    const narrow = window.matchMedia('(max-width: 640px)');
    const syncHistory = () => {
      const collapsed = history.classList.contains('collapsed');
      history.inert = collapsed;
      historyToggle.setAttribute('aria-expanded', String(!collapsed));
      historyToggle.setAttribute('aria-controls', 'sidebar');
      historyToggle.setAttribute('aria-label', collapsed ? 'Show conversation history' : 'Hide conversation history');
    };
    if (narrow.matches) history.classList.add('collapsed');
    const observer = new MutationObserver(syncHistory);
    observer.observe(history, { attributes: true, attributeFilter: ['class'] });
    narrow.addEventListener('change', () => {
      history.classList.toggle('collapsed', narrow.matches);
      syncHistory();
    });
    syncHistory();
  }
  syncNavigation();
});
