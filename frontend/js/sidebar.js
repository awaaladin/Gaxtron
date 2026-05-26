/** Collapsible dashboard sidebar — icon rail by default, expands on hover */
(function () {
  const sidebar = document.getElementById('dashSidebar');
  if (!sidebar) return;

  let collapseTimer = null;

  function expand() {
    clearTimeout(collapseTimer);
    sidebar.classList.add('is-expanded');
  }

  function collapse() {
    clearTimeout(collapseTimer);
    collapseTimer = setTimeout(() => {
      sidebar.classList.remove('is-expanded');
    }, 80);
  }

  sidebar.addEventListener('mouseenter', expand);
  sidebar.addEventListener('mouseleave', collapse);
  sidebar.addEventListener('focusin', expand);
  sidebar.addEventListener('focusout', (e) => {
    if (!sidebar.contains(e.relatedTarget)) collapse();
  });
})();
