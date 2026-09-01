import { Link, NavLink } from "react-router-dom";

function tabClass({ isActive }: { isActive: boolean }) {
  return isActive ? "style-tab style-tab-active" : "style-tab";
}

/** Shared chrome for the three style-detail screens: a "Styles / {name}"
 * breadcrumb plus a Bulletin | Operations | Analytics tab strip, replacing
 * each page's previous ad hoc cross-link buttons (see UI_UX_PLAN.md
 * section 2). `styleName` is optional because BulletinPage/AnalyticsPage
 * only know it once their own fetch resolves. */
export function StyleTabs({ styleId, styleName }: { styleId: string; styleName?: string }) {
  return (
    <div className="style-tabs-wrap">
      <div className="breadcrumb">
        <Link to="/styles">Styles</Link>
        <span aria-hidden="true"> / </span>
        <span>{styleName ?? "…"}</span>
      </div>
      <nav className="style-tabs" aria-label="Style sections">
        <NavLink to={`/styles/${styleId}/bulletin`} className={tabClass} end>
          Bulletin
        </NavLink>
        <NavLink to={`/styles/${styleId}/edit`} className={tabClass} end>
          Operations
        </NavLink>
        <NavLink to={`/styles/${styleId}/analytics`} className={tabClass} end>
          Analytics
        </NavLink>
      </nav>
    </div>
  );
}
