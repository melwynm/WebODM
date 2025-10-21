import React from 'react';
import PropTypes from 'prop-types';
import './css/Dashboard.scss';
import ProjectList from './components/ProjectList';
import EditProjectDialog from './components/EditProjectDialog';
import Utils from './classes/Utils';
import {
  BrowserRouter as Router,
  Route
} from 'react-router-dom';
import $ from 'jquery';
import { _ } from './classes/gettext';

class Dashboard extends React.Component {
  static defaultProps = {
    permissions: []
  };
  static propTypes = {
    permissions: PropTypes.array.isRequired,
  };

  constructor(props){
    super(props);

    this.handleAddProject = this.handleAddProject.bind(this);
    this.addNewProject = this.addNewProject.bind(this);
  }

  handleAddProject(){
    this.projectDialog.show();
  }

  addNewProject(project){
    if (!project.name) return (new $.Deferred()).reject(_("Name field is required"));

    return $.ajax({
          url: `/api/projects/`,
          type: 'POST',
          contentType: 'application/json',
          data: JSON.stringify({
            name: project.name,
            description: project.descr,
            tags: project.tags
          })
      }).done(() => {
        this.projectList.refresh();
      });
    }
    
  render() {
    const projectList = ({ location, history }) => {
      let q = Utils.queryParams(location);
      if (q.page === undefined) q.page = 1;
      else q.page = parseInt(q.page);

      return <ProjectList
                source={`/api/projects/${Utils.toSearchQuery(q)}`}
                ref={(domNode) => { this.projectList = domNode; }} 
                currentPage={q.page}
                currentSearch={q.search}
                history={history}
                />;
    };


    const canCreateProjects = this.props.permissions.indexOf("add_project") !== -1;

    return (
      <Router basename="/dashboard">
        <div className="dashboard-app">
          <div className="dashboard-hero">
            <div className="dashboard-hero__text">
              <h1>{_("Your Projects")}</h1>
              <p>{_("Track progress, upload new datasets and collaborate with ease from your modernized dashboard.")}</p>
            </div>
            {canCreateProjects ?
              <div className="dashboard-hero__actions">
                <button
                  type="button"
                  className="btn btn-primary btn-modern"
                  onClick={this.handleAddProject}>
                  <span className="btn-modern__icon" aria-hidden="true">
                    <i className="fas fa-plus"></i>
                  </span>
                  <span className="btn-modern__label">{_("Add Project")}</span>
                </button>
              </div>
            : ""}
          </div>

          <EditProjectDialog
            saveAction={this.addNewProject}
            ref={(domNode) => { this.projectDialog = domNode; }}
            />

          <div className="dashboard-list-wrapper">
            <Route path="/" component={projectList} />
          </div>
        </div>
      </Router>
    );
  }
}

$(function(){
    $("[data-dashboard]").each(function(){
        let props = $(this).data();
        delete(props.dashboard);
        window.ReactDOM.render(<Dashboard {...props}/>, $(this).get(0));
    });

    // Warn users if there's any sort of work in progress before
    // they press the back button on the browser
    // Yes it's a hack. No we're not going to track state in React just
    // for this.
    window.onbeforeunload = function() {
        let found = false; 
        $(".progress-bar:visible").each(function(){ 
            try{
                let value = parseFloat($(this).text());
                if (!isNaN(value) && value > 0 && value < 100) found = true;
            }catch(e){
                // Do nothing
            }
        });
        return found ? _("Your changes will be lost. Are you sure you want to leave?") : undefined; 
    };
});

export default Dashboard;
