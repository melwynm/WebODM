import React from 'react';
import $ from 'jquery';
import '../css/ProjectList.scss';

import ProjectListItem from './ProjectListItem';
import Paginated from './Paginated';
import Paginator from './Paginator';
import ErrorMessage from './ErrorMessage';
import { _, interpolate } from '../classes/gettext';
import PropTypes from 'prop-types';
import Utils from '../classes/Utils';
import StatusCodes from '../classes/StatusCodes';

class ProjectList extends Paginated {
    static propTypes = {
        history: PropTypes.object.isRequired,
    }

    constructor(props){
        super(props);

        this.state = {
            loading: true,
            refreshing: false,
            error: "",
            projects: []
        };

        this.PROJECTS_PER_PAGE = 10;

        this.handleDelete = this.handleDelete.bind(this);
    }

    componentDidMount(){
        this.refresh();
    }

    getParametersHash(source){
        if (!source) return "";
        if (source.indexOf("?") === -1) return "";

        let search = source.substr(source.indexOf("?"));
        let q = Utils.queryParams({search});

        // All parameters that can change via history.push without
        // triggering a reload of the project list should go here
        delete q.project_task_open;
        delete q.project_task_expanded;

        return JSON.stringify(q);
    }

    componentDidUpdate(prevProps){
        if (this.getParametersHash(prevProps.source) !== this.getParametersHash(this.props.source)){
            this.refresh();
        }
    }

    refresh(){
        this.setState({refreshing: true});

        // Load projects from API
        this.serverRequest =
            $.getJSON(this.props.source, json => {
                if (json.results){
                    this.setState({
                        projects: json.results,
                        loading: false
                    });
                    this.updatePagination(this.PROJECTS_PER_PAGE, json.count);
                }else{
                    this.setState({
                        error: interpolate(_("Invalid JSON response: %(error)s"), {error: JSON.stringify(json)}),
                        loading: false
                    });
                }
            })
            .fail((jqXHR, textStatus, errorThrown) => {
                this.setState({
                    error: interpolate(_("Could not load projects list: %(error)s"), {error: textStatus}),
                    loading: false
                });
            })
            .always(() => {
                this.setState({refreshing: false});
            });
    }

    onPageChanged(pageNum){
        this.refresh();
    }

    componentWillUnmount(){
        this.serverRequest.abort();
    }

    handleDelete(projectId){
        let projects = this.state.projects.filter(p => p.id !== projectId);
        this.setState({projects: projects});
        this.handlePageItemsNumChange(-1, () => {
            this.refresh();
        });
    }

    handleTaskMoved = (task) => {
        if (this["projectListItem_" + task.project]){
            this["projectListItem_" + task.project].newTaskAdded();
        }
    }

    handleProjectDuplicated = () => {
        this.refresh();
    }

    render() {
        if (this.state.loading){
            return (<div className="project-list text-center"><i className="fa fa-circle-notch fa-spin fa-2x fa-fw"></i></div>);
        }else{
            const hasProjects = this.state.projects.length > 0;
            const emptyMessage = this.props.currentSearch ?
                _("No projects match this search yet.") :
                _("Create a new project to start organizing flights, maps and reports.");
            const totalProjects = this.state.pagination && this.state.pagination.totalItems !== undefined ?
                this.state.pagination.totalItems :
                this.state.projects.length;
            const activeTasks = this.state.projects.reduce((count, project) => {
                return count + (project.tasks_count !== undefined ? project.tasks_count : ((project.tasks || []).length || 0));
            }, 0);
            const processingTasks = this.state.projects.reduce((count, project) => {
                if (project.processing_tasks_count !== undefined) return count + project.processing_tasks_count;

                return count + (project.tasks || []).filter(task => {
                    return task && typeof task === 'object' && task.status !== undefined && task.status !== StatusCodes.COMPLETED;
                }).length;
            }, 0);

            return (<div className="project-list">
                <ErrorMessage bind={[this, 'error']} />
                <div className="project-stats-row" aria-label={_("Project statistics")}>
                    <div className="project-stat-card">
                        <span className="project-stat-card__icon" aria-hidden="true"><i className="fa fa-th-large"></i></span>
                        <span className="project-stat-card__body">
                            <strong>{totalProjects}</strong>
                            <span>{_("Total Projects")}</span>
                        </span>
                    </div>
                    <div className="project-stat-card">
                        <span className="project-stat-card__icon" aria-hidden="true"><i className="fa fa-tasks"></i></span>
                        <span className="project-stat-card__body">
                            <strong>{activeTasks}</strong>
                            <span>{_("Active Tasks")}</span>
                        </span>
                    </div>
                    <div className="project-stat-card">
                        <span className="project-stat-card__icon" aria-hidden="true"><i className="fa fa-bolt"></i></span>
                        <span className="project-stat-card__body">
                            <strong>{processingTasks}</strong>
                            <span>{_("Processing")}</span>
                        </span>
                    </div>
                </div>
                <Paginator {...this.state.pagination} {...this.props}>
                    {hasProjects ?
                        <ul
                            key="1"
                            className={`project-grid list-group ${this.state.refreshing ? "refreshing" : ""}`}>
                            {this.state.projects.map(p => (
                                <ProjectListItem
                                    ref={(domNode) => { this["projectListItem_" + p.id] = domNode; }}
                                    key={p.id}
                                    data={p}
                                    onDelete={this.handleDelete}
                                    onTaskMoved={this.handleTaskMoved}
                                    onProjectDuplicated={this.handleProjectDuplicated}
                                    history={this.props.history} />
                            ))}
                        </ul>
                    :
                        <div className="project-list-empty">
                            <div className="project-list-empty__icon" aria-hidden="true">
                                <i className="fa fa-map-o"></i>
                            </div>
                            <h3>{_("Your workspace is ready")}</h3>
                            <p>{emptyMessage}</p>
                        </div>}
                </Paginator>
            </div>);
        }
    }
}

export default ProjectList;
