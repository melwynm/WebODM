import React from 'react';
import { shallow } from 'enzyme';
import $ from 'jquery';

import MonitoringRunPanel from '../MonitoringRunPanel';

const completedRequest = payload => {
  const request = {
    done: callback => {
      callback(payload);
      return request;
    },
    fail: () => request,
    always: callback => {
      callback();
      return request;
    },
    abort: jest.fn()
  };
  return request;
};

const deferredRequest = () => {
  const callbacks = {done: [], fail: [], always: []};
  const request = {
    done: callback => {
      callbacks.done.push(callback);
      return request;
    },
    fail: callback => {
      callbacks.fail.push(callback);
      return request;
    },
    always: callback => {
      callbacks.always.push(callback);
      return request;
    },
    abort: jest.fn(),
    resolve: payload => {
      callbacks.done.forEach(callback => callback(payload));
      callbacks.always.forEach(callback => callback());
    },
    reject: error => {
      callbacks.fail.forEach(callback => callback(error));
      callbacks.always.forEach(callback => callback());
    }
  };
  return request;
};

const timeline = {
  results: [
    {id: 'baseline-task', name: 'Baseline survey'},
    {id: 'current-task', name: 'Current survey'}
  ],
  default_reference_task_id: 'current-task',
  default_compare_task_id: 'baseline-task'
};

const reviewRun = {
  id: 'run-1',
  project: 7,
  current_task: 'current-task',
  current_task_detail: {id: 'current-task', name: 'Current survey'},
  baseline_task: 'baseline-task',
  baseline_task_detail: {id: 'baseline-task', name: 'Baseline survey'},
  status: 'review',
  status_label: 'Ready for review',
  issue_count: 0,
  issues: [],
  can_publish: true,
  report_url: '/report'
};

const otherRun = {
  ...reviewRun,
  id: 'run-2',
  current_task: 'older-task',
  current_task_detail: {id: 'older-task', name: 'Older survey'},
  status_label: 'Ready for review'
};

describe('<MonitoringRunPanel />', () => {
  beforeEach(() => {
    jest.spyOn($, 'getJSON').mockImplementation(url => {
      if (url.indexOf('/monitoring/timeline') !== -1) return completedRequest(timeline);
      return completedRequest([]);
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('starts a run with the suggested current and baseline surveys', () => {
    const ajax = jest.spyOn($, 'ajax').mockImplementation(() => completedRequest(reviewRun));
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);

    wrapper.find('form.monitoring-run-setup').simulate('submit', {preventDefault: jest.fn()});

    expect(JSON.parse(ajax.mock.calls[0][0].data)).toEqual({
      current_task: 'current-task',
      baseline_task: 'baseline-task'
    });
    expect(wrapper.find('.monitoring-run-review')).toHaveLength(1);
    expect(wrapper.text()).toContain('Current survey');
    expect(wrapper.text()).toContain('Baseline survey');
  });

  it('previews exact-pair AI findings and confirms the signed result', () => {
    const preview = {
      candidates: [{
        title: 'Review surface change',
        description: 'A concentrated change is visible.',
        priority: 'high',
        issue_type: 'change'
      }],
      confirmation_token: 'signed-monitoring-preview'
    };
    const ajax = jest.spyOn($, 'ajax')
      .mockImplementationOnce(() => completedRequest(preview))
      .mockImplementationOnce(() => completedRequest({issues: [{id: 8}]}));
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);
    wrapper.setState({currentRun: reviewRun, runs: [reviewRun], loading: false});
    jest.spyOn(wrapper.instance(), 'refreshRun').mockImplementation(() => {});

    wrapper.find('.monitoring-run-actions button').filterWhere(button => button.text().indexOf('AI review') !== -1).simulate('click');

    expect(JSON.parse(ajax.mock.calls[0][0].data)).toEqual({
      source: 'monitoring_change',
      task: 'current-task',
      compare_task: 'baseline-task',
      monitoring_run: 'run-1',
      max_images: 1,
      create: false
    });
    expect(wrapper.text()).toContain('Review surface change');

    wrapper.find('.monitoring-ai-preview button').simulate('click');

    expect(JSON.parse(ajax.mock.calls[1][0].data)).toEqual({
      confirmation_token: 'signed-monitoring-preview',
      create: true
    });
    expect(wrapper.instance().refreshRun).toHaveBeenCalledWith('run-1');
    expect(wrapper.find('.monitoring-ai-preview button')).toHaveLength(0);
  });

  it('publishes the reviewed run and exposes the client portal action', () => {
    const published = {
      ...reviewRun,
      status: 'published',
      status_label: 'Published',
      can_publish: false,
      portal_url: '/client/projects/token/'
    };
    const ajax = jest.spyOn($, 'ajax').mockImplementation(() => completedRequest(published));
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);
    wrapper.setState({currentRun: reviewRun, runs: [reviewRun], loading: false});

    wrapper.find('.monitoring-run-actions button').filterWhere(button => button.text().indexOf('Publish') !== -1).simulate('click');

    expect(ajax.mock.calls[0][0].url).toContain('/monitoring-runs/run-1/publish/');
    expect(wrapper.text()).toContain('Open client portal');
    expect(wrapper.state('currentRun').status).toBe('published');
  });

  it('ignores an old polling response after another run is selected', () => {
    const pendingRefresh = deferredRequest();
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);
    wrapper.setState({currentRun: reviewRun, runs: [reviewRun, otherRun], loading: false});
    $.getJSON.mockImplementationOnce(() => pendingRefresh);

    wrapper.instance().refreshRun(reviewRun.id);
    wrapper.find('.monitoring-run-header select').simulate('change', {target: {value: otherRun.id}});
    pendingRefresh.resolve({...reviewRun, status: 'published', status_label: 'Published'});

    expect(pendingRefresh.abort).toHaveBeenCalled();
    expect(wrapper.state('currentRun').id).toBe(otherRun.id);
    expect(wrapper.state('currentRun').status).toBe('review');
  });

  it('cancels an AI preview and ignores its response when another run is selected', () => {
    const pendingPreview = deferredRequest();
    jest.spyOn($, 'ajax').mockImplementation(() => pendingPreview);
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);
    wrapper.setState({currentRun: reviewRun, runs: [reviewRun, otherRun], loading: false});

    wrapper.find('.monitoring-run-actions button').filterWhere(button => button.text().indexOf('AI review') !== -1).simulate('click');
    expect(wrapper.state('previewingAI')).toBe(true);

    wrapper.find('.monitoring-run-header select').simulate('change', {target: {value: otherRun.id}});
    pendingPreview.resolve({candidates: [{title: 'Stale candidate'}], confirmation_token: 'stale-token'});

    expect(pendingPreview.abort).toHaveBeenCalled();
    expect(wrapper.state('currentRun').id).toBe(otherRun.id);
    expect(wrapper.state('aiPreview')).toBe(null);
    expect(wrapper.state('previewingAI')).toBe(false);
  });

  it('locks run selection and prevents duplicate mutations while publishing', () => {
    const pendingPublish = deferredRequest();
    const ajax = jest.spyOn($, 'ajax').mockImplementation(() => pendingPublish);
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);
    wrapper.setState({currentRun: reviewRun, runs: [reviewRun, otherRun], loading: false});

    const publishButton = () => wrapper.find('.monitoring-run-actions button')
      .filterWhere(button => button.text().indexOf('Publish') !== -1);
    publishButton().simulate('click');

    expect(wrapper.find('.monitoring-run-header select').prop('disabled')).toBe(true);
    expect(publishButton().prop('disabled')).toBe(true);
    publishButton().simulate('click');
    wrapper.instance().selectRun({target: {value: otherRun.id}});

    expect(ajax).toHaveBeenCalledTimes(1);
    expect(wrapper.state('currentRun').id).toBe(reviewRun.id);

    pendingPublish.resolve({
      ...reviewRun,
      status: 'published',
      status_label: 'Published',
      can_publish: false,
      portal_url: '/client/projects/token/'
    });

    expect(wrapper.state('publishing')).toBe(false);
    expect(wrapper.state('currentRun').status).toBe('published');
  });

  it('restores run actions after a mutation fails', () => {
    const pendingPublish = deferredRequest();
    jest.spyOn($, 'ajax').mockImplementation(() => pendingPublish);
    const wrapper = shallow(<MonitoringRunPanel projectId={7} />);
    wrapper.setState({currentRun: reviewRun, runs: [reviewRun, otherRun], loading: false});

    wrapper.find('.monitoring-run-actions button').filterWhere(button => button.text().indexOf('Publish') !== -1).simulate('click');
    pendingPublish.reject({responseJSON: {detail: 'Publication unavailable'}});

    expect(wrapper.state('publishing')).toBe(false);
    expect(wrapper.find('.monitoring-run-header select').prop('disabled')).toBe(false);
    expect(wrapper.text()).toContain('Publication unavailable');
  });
});
