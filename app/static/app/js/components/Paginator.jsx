import React from 'react';
import '../css/Paginator.scss';
import { Link, withRouter } from 'react-router-dom';
import SortPanel from './SortPanel';
import Utils from '../classes/Utils';
import { _, interpolate } from '../classes/gettext';

let decodeSearch = (search) => {
    return window.decodeURI(search.replace(/:/g, "#"));
};

class Paginator extends React.Component {
    constructor(props){
        super(props);

        const q = Utils.queryParams(props.location);
        
        this.state = {
            searchText: decodeSearch(q.search || ""),
            sortKey: q.ordering || "-created_at"
        };

        this.sortItems = [{
            key: "created_at",
            label: _("Created on")
          },{
            key: "name",
            label: _("Name")
          },{
            key: "tags",
            label: _("Tags")
          },{
            key: "owner",
            label: _("Owner")
          }];
    }

    componentDidMount(){
        document.addEventListener("onProjectListTagClicked", this.addTagAndSearch);
    }

    componentWillUnmount(){
        document.removeEventListener("onProjectListTagClicked", this.addTagAndSearch);
    }

    handleSearchChange = e => {
        this.setState({searchText: e.target.value});
    }

    handleSearchKeyDown = e => {
        if (e.key === "Enter"){
            this.search();
        }
    }
    
    search = () => {
        this.props.history.push({search: this.getQueryForPage(1)});
    }

    clearSearch = () => {
        this.setState({searchText: ""});
        setTimeout(() => {
            this.search();
        }, 0);
    }

    sortChanged = key => {
        this.setState({sortKey: key});
        setTimeout(() => {
            this.props.history.push({search: this.getQueryForPage(this.props.currentPage)});
        }, 0);
    }

    getQueryForPage = (num) => {
        return Utils.toSearchQuery({
            page: num,
            ordering: this.state.sortKey,
            search: this.state.searchText.replace(/#/g, ":")
        });
    }

    addTagAndSearch = e => {
        const tag = e.detail;
        if (tag === undefined) return;

        let { searchText } = this.state;
        if (searchText === "") searchText += "#" + tag;
        else searchText += " #" + tag;

        this.setState({searchText});
        setTimeout(() => {
            this.search();
        }, 0);
    }

    getSelectedSortLabel = () => {
        const normalizedSortKey = this.state.sortKey.replace("-", "");
        const selectedSort = this.sortItems.find(item => item.key === normalizedSortKey);
        return selectedSort ? selectedSort.label : _("Created on");
    }

    getSelectedSortDirection = () => {
        return this.state.sortKey[0] === "-" ? _("Descending") : _("Ascending");
    }

    render() {
        const { itemsPerPage, totalItems, currentPage } = this.props;
        const { searchText } = this.state;

        let paginator = null;
        let clearSearch = null;

        const toolbar = (
            <div className="paginator-toolbar">
                <div className="paginator-summary">
                    <span className="paginator-summary__eyebrow">{_("Workspace")}</span>
                    <strong className="paginator-summary__value">
                        {interpolate(_("%(count)s projects"), {count: totalItems || 0})}
                    </strong>
                </div>

                <div className="paginator-controls">
                    <div className="paginator-search-shell theme-border-secondary-07">
                        <span className="paginator-search-icon" aria-hidden="true">
                            <i className="fa fa-search"></i>
                        </span>
                        <input
                            type="text"
                            ref={(domNode) => { this.searchInput = domNode; }}
                            className="form-control search theme-border-secondary-07"
                            placeholder={_("Search names, #tags or @user")}
                            spellCheck="false"
                            autoComplete="false"
                            value={searchText}
                            onKeyDown={this.handleSearchKeyDown}
                            onChange={this.handleSearchChange} />
                        {searchText ?
                            <button type="button" className="paginator-search-clear" title={_("Clear search")} onClick={this.clearSearch}>
                                <i className="fa fa-times"></i>
                            </button>
                        : ""}
                        <button type="button" onClick={this.search} className="btn btn-primary btn-modern paginator-search-submit">
                            <span className="btn-modern__icon" aria-hidden="true">
                                <i className="fa fa-search"></i>
                            </span>
                            <span className="btn-modern__label">{_("Search")}</span>
                        </button>
                    </div>

                    <div className="btn-group paginator-sort">
                        <button
                            type="button"
                            className="btn btn-default btn-modern dropdown-toggle"
                            data-toggle="dropdown"
                            aria-haspopup="true"
                            aria-expanded="false">
                            <span className="btn-modern__icon" aria-hidden="true">
                                <i className="fa fa-sort-alpha-down"></i>
                            </span>
                            <span className="btn-modern__label">
                                {this.getSelectedSortLabel()}
                                <span className="paginator-sort-order">{this.getSelectedSortDirection()}</span>
                            </span>
                        </button>
                        <SortPanel selected={this.state.sortKey} items={this.sortItems} onChange={this.sortChanged} />
                    </div>
                </div>
            </div>
        );

        if (this.props.currentSearch){
            let currentSearch = decodeSearch(this.props.currentSearch);
            clearSearch = (
                <span className="clear-search">
                    <span className="clear-search__label">{_("Search results for:")}</span>
                    <span className="query">{currentSearch}</span>
                    <button type="button" className="clear-search__button" onClick={this.clearSearch} title={_("Clear search")}>
                        <i className="fa fa-times"></i>
                    </button>
                </span>
            );
        }

        if (itemsPerPage && itemsPerPage && totalItems > itemsPerPage){
            const numPages = Math.ceil(totalItems / itemsPerPage);
            const MAX_PAGE_BUTTONS = 7;

            let rangeStart = Math.max(1, currentPage - Math.floor(MAX_PAGE_BUTTONS / 2));
            let rangeEnd = rangeStart + Math.min(numPages, MAX_PAGE_BUTTONS);
            if (rangeEnd > numPages){
                rangeStart -= rangeEnd - numPages - 1;
                rangeEnd -= rangeEnd - numPages - 1;
            }
            let pages = [...Array(rangeEnd - rangeStart).keys()].map(i => i + rangeStart - 1);
            
            paginator = (
                <ul className="pagination pagination-sm">
                    <li className={currentPage === 1 ? "disabled" : ""}>
                      <Link to={{search: this.getQueryForPage(1)}}>
                        <span>&laquo;</span>
                      </Link>
                    </li>
                    {pages.map(page => {
                        return (<li
                            key={page + 1}
                            className={currentPage === (page + 1) ? "active" : ""}
                        ><Link to={{search: this.getQueryForPage(page + 1)}}>{page + 1}</Link></li>);
                    })}
                    <li className={currentPage === numPages ? "disabled" : ""}>
                      <Link to={{search: this.getQueryForPage(numPages)}}>
                        <span>&raquo;</span>
                      </Link>
                    </li>
                </ul>
              );
        }

        return [
            <div key="0" className="paginator">{toolbar}{clearSearch}{paginator}</div>,
            this.props.children,
            <div key="2" className="paginator paginator-bottom">{paginator}</div>,
        ];
    }
}

export default withRouter(Paginator);
