(function(){
  const load = () => Promise.all([
    PluginsAPI.SystemJS.import('React'),
    PluginsAPI.SystemJS.import('ReactDOM')
  ]);

  function getCSRFToken(){
    const name = 'csrftoken=';
    const decoded = decodeURIComponent(document.cookie || '');
    const parts = decoded.split(';');
    for (let i = 0; i < parts.length; i++){
      let c = parts[i].trim();
      if (c.indexOf(name) === 0){
        return c.substring(name.length);
      }
    }
    return null;
  }

  function formatDate(dateStr){
    if (!dateStr) return '-';
    try{
      const date = new Date(dateStr);
      if (!isNaN(date.getTime())){
        return date.toLocaleDateString();
      }
    }catch(err){
      return dateStr;
    }
    return dateStr;
  }

  function sanitizeFileName(name){
    if (!name) return 'mission';
    return name.replace(/[^a-z0-9\-_.]+/gi, '_');
  }

  load().then(function(modules){
    const React = modules[0].default || modules[0];
    const ReactDOM = modules[1].default || modules[1];
    const h = React.createElement;

    class MissionPlannerManager extends React.Component{
      constructor(props){
        super(props);
        this.state = {
          open: false,
          projectId: null,
          missions: [],
          loading: false,
          error: '',
          saving: false,
          deleting: false,
          editingId: null,
          form: {
            name: '',
            notes: '',
            captureDate: '',
            geometry: ''
          },
          fileName: ''
        };
        this.pendingFile = null;

        this.open = this.open.bind(this);
        this.close = this.close.bind(this);
        this.fetchMissions = this.fetchMissions.bind(this);
        this.handleChange = this.handleChange.bind(this);
        this.handleSubmit = this.handleSubmit.bind(this);
        this.handleDelete = this.handleDelete.bind(this);
        this.handleEdit = this.handleEdit.bind(this);
        this.resetForm = this.resetForm.bind(this);
        this.handleFileChange = this.handleFileChange.bind(this);
        this.downloadMission = this.downloadMission.bind(this);
        this.renderMissionTable = this.renderMissionTable.bind(this);
      }

      open(projectId){
        this.setState({
          open: true,
          projectId: projectId,
          missions: [],
          loading: true,
          error: '',
          saving: false,
          deleting: false,
          editingId: null,
          form: {name: '', notes: '', captureDate: '', geometry: ''},
          fileName: ''
        }, this.fetchMissions);
      }

      close(){
        this.setState({open: false});
      }

      setError(message){
        this.setState({error: message || ''});
      }

      fetchMissions(){
        const projectId = this.state.projectId;
        if (!projectId) return;
        this.setState({loading: true});
        fetch(`/api/plugins/mission_planner/project/${projectId}/missions`, {
          credentials: 'same-origin'
        }).then(response => {
          if (!response.ok){
            throw new Error('Unable to load mission plans.');
          }
          return response.json();
        }).then(json => {
          this.setState({missions: json.missions || [], loading: false});
        }).catch(err => {
          this.setError(err.message);
          this.setState({loading: false});
        });
      }

      handleChange(field, event){
        const value = event.target.value;
        this.setState(prev => ({
          form: Object.assign({}, prev.form, {[field]: value})
        }));
      }

      handleFileChange(event){
        const files = event.target.files;
        if (files && files.length){
          this.pendingFile = files[0];
          this.setState({fileName: files[0].name});
        }else{
          this.pendingFile = null;
          this.setState({fileName: ''});
        }
      }

      resetForm(){
        this.pendingFile = null;
        if (this.fileInput){
          this.fileInput.value = '';
        }
        this.setState({
          editingId: null,
          form: {name: '', notes: '', captureDate: '', geometry: ''},
          fileName: ''
        });
      }

      handleSubmit(event){
        event.preventDefault();
        if (this.state.saving) return;

        const projectId = this.state.projectId;
        if (!projectId) return;

        const formData = new FormData();
        const { form } = this.state;
        formData.append('name', form.name || '');
        formData.append('notes', form.notes || '');
        formData.append('capture_date', form.captureDate || '');
        if (form.geometry){
          formData.append('geometry', form.geometry);
        }
        if (this.pendingFile){
          formData.append('plan_file', this.pendingFile);
        }

        const headers = {};
        const csrf = getCSRFToken();
        if (csrf) headers['X-CSRFToken'] = csrf;

        const requestInit = {
          method: this.state.editingId ? 'PATCH' : 'POST',
          body: formData,
          headers: headers,
          credentials: 'same-origin'
        };

        let url = `/api/plugins/mission_planner/project/${projectId}/missions`;
        if (this.state.editingId){
          url += `/${this.state.editingId}`;
        }

        this.setState({saving: true, error: ''});
        fetch(url, requestInit).then(response => {
          if (!response.ok){
            return response.json().then(json => {
              const msg = json && json.error ? json.error : 'Unable to save mission plan.';
              throw new Error(msg);
            }).catch(() => {
              throw new Error('Unable to save mission plan.');
            });
          }
          return response.json();
        }).then(() => {
          this.pendingFile = null;
          if (this.fileInput){
            this.fileInput.value = '';
          }
          this.setState({saving: false, editingId: null, form: {name: '', notes: '', captureDate: '', geometry: ''}, fileName: ''});
          this.fetchMissions();
        }).catch(err => {
          this.setState({saving: false});
          this.setError(err.message);
        });
      }

      handleDelete(mission){
        if (!mission || this.state.deleting) return;
        if (!window.confirm('Delete this mission plan?')) return;

        const projectId = this.state.projectId;
        const headers = {};
        const csrf = getCSRFToken();
        if (csrf) headers['X-CSRFToken'] = csrf;

        this.setState({deleting: true, error: ''});
        fetch(`/api/plugins/mission_planner/project/${projectId}/missions/${mission.id}`, {
          method: 'DELETE',
          headers: headers,
          credentials: 'same-origin'
        }).then(response => {
          if (!response.ok && response.status !== 204){
            return response.json().then(json => {
              const msg = json && json.error ? json.error : 'Unable to delete mission plan.';
              throw new Error(msg);
            }).catch(() => {
              throw new Error('Unable to delete mission plan.');
            });
          }
        }).then(() => {
          this.setState({deleting: false});
          if (this.state.editingId === mission.id){
            this.resetForm();
          }
          this.fetchMissions();
        }).catch(err => {
          this.setState({deleting: false});
          this.setError(err.message);
        });
      }

      handleEdit(mission){
        if (!mission) return;
        const form = {
          name: mission.name || '',
          notes: mission.notes || '',
          captureDate: mission.capture_date || '',
          geometry: mission.source === 'manual' && mission.geometry ? JSON.stringify(mission.geometry, null, 2) : ''
        };
        this.pendingFile = null;
        if (this.fileInput){
          this.fileInput.value = '';
        }
        this.setState({editingId: mission.id, form: form, fileName: mission.file_name || ''});
      }

      downloadMission(mission){
        if (!mission || !mission.geometry) return;
        const content = JSON.stringify(mission.geometry, null, 2);
        const blob = new Blob([content], {type: 'application/geo+json'});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const baseName = sanitizeFileName(mission.name || 'mission');
        link.href = url;
        link.download = `${baseName}.geojson`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function(){ URL.revokeObjectURL(url); }, 0);
      }

      renderMissionTable(){
        const missions = this.state.missions || [];
        if (!missions.length){
          return h('div', {className: 'mission-planner-empty'}, 'No mission plans yet.');
        }

        const rows = missions.map(mission => {
          const dateLabel = formatDate(mission.capture_date);
          const sourceLabel = mission.source === 'upload' ? 'Upload' : 'Manual';
          const fileLabel = mission.file_name ? ` (${mission.file_name})` : '';
          const actions = h('div', {className: 'mission-planner-actions'}, [
            h('button', {
              key: 'download',
              type: 'button',
              className: 'btn btn-xs btn-default',
              onClick: () => this.downloadMission(mission)
            }, h('i', {className: 'fa fa-download'}), ' Download'),
            h('button', {
              key: 'edit',
              type: 'button',
              className: 'btn btn-xs btn-primary',
              onClick: () => this.handleEdit(mission)
            }, h('i', {className: 'fa fa-edit'}), ' Edit'),
            h('button', {
              key: 'delete',
              type: 'button',
              className: 'btn btn-xs btn-danger',
              onClick: () => this.handleDelete(mission)
            }, h('i', {className: 'fa fa-trash'}), ' Delete')
          ]);
          return h('tr', {key: mission.id}, [
            h('td', null, mission.name || 'Untitled mission'),
            h('td', null, dateLabel),
            h('td', null, sourceLabel + fileLabel),
            h('td', null, mission.notes || ''),
            h('td', null, actions)
          ]);
        });

        return h('table', {className: 'mission-planner-table'}, [
          h('thead', {key: 'head'}, h('tr', null, [
            h('th', {key: 'name'}, 'Name'),
            h('th', {key: 'date'}, 'Capture Date'),
            h('th', {key: 'source'}, 'Source'),
            h('th', {key: 'notes'}, 'Notes'),
            h('th', {key: 'actions'}, 'Actions')
          ])),
          h('tbody', {key: 'body'}, rows)
        ]);
      }

      render(){
        if (!this.state.open){
          return null;
        }

        const chips = [
          h('span', {key: 'count', className: 'mission-planner-chip'}, `${this.state.missions.length} saved mission(s)`)];
        if (this.state.fileName){
          chips.push(h('span', {key: 'file', className: 'mission-planner-chip'}, `Attached file: ${this.state.fileName}`));
        }
        if (this.state.editingId){
          chips.push(h('span', {key: 'editing', className: 'mission-planner-chip'}, 'Editing existing mission'));
        }

        return h('div', {className: 'mission-planner-overlay'},
          h('div', {className: 'mission-planner-modal'}, [
            h('div', {className: 'mission-planner-header'}, [
              h('h4', {className: 'modal-title'}, 'Mission Planner'),
              h('button', {
                type: 'button',
                className: 'close',
                onClick: this.close,
                title: 'Close'
              }, '\u00d7')
            ]),
            h('div', {className: 'mission-planner-body'}, [
              this.state.error ? h('div', {className: 'alert alert-danger'}, this.state.error) : null,
              h('form', {className: 'mission-planner-form', onSubmit: this.handleSubmit}, [
                h('div', {className: 'row'}, [
                  h('div', {className: 'col-sm-6'}, [
                    h('div', {className: 'form-group'}, [
                      h('label', null, 'Mission name'),
                      h('input', {
                        type: 'text',
                        className: 'form-control',
                        value: this.state.form.name,
                        onChange: (e) => this.handleChange('name', e),
                        placeholder: 'Survey name or flight path'
                      })
                    ])
                  ]),
                  h('div', {className: 'col-sm-6'}, [
                    h('div', {className: 'form-group'}, [
                      h('label', null, 'Capture date'),
                      h('input', {
                        type: 'date',
                        className: 'form-control',
                        value: this.state.form.captureDate,
                        onChange: (e) => this.handleChange('captureDate', e)
                      })
                    ])
                  ])
                ]),
                h('div', {className: 'form-group'}, [
                  h('label', null, 'Notes'),
                  h('textarea', {
                    className: 'form-control',
                    rows: 2,
                    value: this.state.form.notes,
                    onChange: (e) => this.handleChange('notes', e),
                    placeholder: 'Flight objectives, pilot, weather, etc.'
                  })
                ]),
                h('div', {className: 'form-group'}, [
                  h('label', null, 'Upload GeoJSON or KML'),
                  h('input', {
                    type: 'file',
                    accept: '.json,.geojson,.kml',
                    className: 'form-control',
                    ref: (ref) => { this.fileInput = ref; },
                    onChange: this.handleFileChange
                  })
                ]),
                h('div', {className: 'form-group'}, [
                  h('label', null, 'Or paste GeoJSON'),
                  h('textarea', {
                    className: 'form-control',
                    rows: 4,
                    value: this.state.form.geometry,
                    onChange: (e) => this.handleChange('geometry', e),
                    placeholder: '{ "type": "FeatureCollection", ... }'
                  })
                ]),
                h('div', {className: 'mission-planner-summary'}, chips)
              ]),
              h('div', {className: 'mission-planner-missions'}, [
                this.state.loading ? h('p', null, 'Loading missions…') : this.renderMissionTable()
              ])
            ]),
            h('div', {className: 'mission-planner-footer'}, [
              this.state.editingId ? h('button', {
                type: 'button',
                className: 'btn btn-link',
                onClick: this.resetForm
              }, 'New mission') : null,
              h('button', {
                type: 'button',
                className: 'btn btn-default',
                onClick: this.close
              }, 'Close'),
              h('button', {
                type: 'submit',
                className: 'btn btn-primary',
                disabled: this.state.saving
              }, this.state.saving ? 'Saving…' : (this.state.editingId ? 'Update mission' : 'Save mission'))
            ])
          ])
        );
      }
    }

    class MissionPlannerButton extends React.Component{
      constructor(props){
        super(props);
        this.handleClick = this.handleClick.bind(this);
      }

      handleClick(){
        if (typeof this.props.onOpen === 'function'){
          this.props.onOpen(this.props.projectId);
        }
      }

      render(){
        return h('button', {
          type: 'button',
          className: 'btn btn-default btn-modern',
          onClick: this.handleClick
        }, [
          h('span', {className: 'btn-modern__icon', 'aria-hidden': 'true'},
            h('i', {className: 'fas fa-route'})
          ),
          h('span', {className: 'btn-modern__label hidden-xs'}, 'Mission Planner')
        ]);
      }
    }

    const container = document.createElement('div');
    container.id = 'mission-planner-root';
    document.body.appendChild(container);
    const managerRef = React.createRef();
    ReactDOM.render(h(MissionPlannerManager, {ref: managerRef}), container);

    function openPlanner(projectId){
      if (managerRef.current){
        managerRef.current.open(projectId);
      }
    }

    PluginsAPI.Dashboard.addNewTaskButton((args) => {
      if (!args || !args.projectId) return null;
      return React.createElement(MissionPlannerButton, {projectId: args.projectId, onOpen: openPlanner});
    });
  }).catch(function(err){
    console.error('Mission Planner plugin failed to initialize:', err);
  });
})();
