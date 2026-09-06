import React from 'react';
import { shallow } from 'enzyme';
import $ from 'jquery';

import AIIssueDetectionPanel from '../AIIssueDetectionPanel';
import ProjectIssuesPanel from '../ProjectIssuesPanel';

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

const issue = {
  id: 42,
  title: 'Review roof edge',
  status: 'open',
  issue_type: 'defect',
  priority: 'high'
};

describe('<ProjectIssuesPanel />', () => {
  beforeEach(() => {
    jest.spyOn($, 'getJSON').mockImplementation(() => completedRequest([]));
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('provides labels, busy state, and an accessible AI review toggle', () => {
    const pending = deferredRequest();
    $.getJSON.mockImplementationOnce(() => pending);
    const wrapper = shallow(<ProjectIssuesPanel projectId={7} canEdit={true} />);

    expect(wrapper.find('section.project-issues-panel').prop('aria-busy')).toBe(true);
    expect(wrapper.find('input#issue-title-7').prop('required')).toBe(true);
    expect(wrapper.find('label[htmlFor="issue-priority-7"]')).toHaveLength(1);
    expect(wrapper.find('button.ai-review-toggle').prop('aria-expanded')).toBe(false);

    wrapper.find('button.ai-review-toggle').simulate('click');
    expect(wrapper.find('button.ai-review-toggle').prop('aria-expanded')).toBe(true);
  });

  it('opens AI review for editors and inserts confirmed issues once', () => {
    const wrapper = shallow(<ProjectIssuesPanel projectId={7} canEdit={true} />);

    expect(wrapper.find(AIIssueDetectionPanel)).toHaveLength(0);
    wrapper.find('button.ai-review-toggle').simulate('click');
    expect(wrapper.find(AIIssueDetectionPanel)).toHaveLength(1);

    const confirmedIssue = {...issue, status: 'in_review'};
    wrapper.find(AIIssueDetectionPanel).props().onIssuesCreated([confirmedIssue]);
    wrapper.find(AIIssueDetectionPanel).props().onIssuesCreated([confirmedIssue]);

    expect(wrapper.state('issues')).toEqual([confirmedIssue]);
    expect(wrapper.text()).toContain('Review roof edge');
  });

  it('does not expose AI review to read-only viewers', () => {
    const wrapper = shallow(<ProjectIssuesPanel projectId={7} canEdit={false} />);
    const ajax = jest.spyOn($, 'ajax');
    wrapper.setState({issues: [issue], loading: false});

    expect(wrapper.find('button.ai-review-toggle')).toHaveLength(0);
    expect(wrapper.find(AIIssueDetectionPanel)).toHaveLength(0);
    expect(wrapper.find('select.project-issue-item__status').prop('disabled')).toBe(true);
    expect(wrapper.find('select.project-issue-item__status').prop('aria-label')).toBe('Status: Review roof edge');

    wrapper.find('select.project-issue-item__status').simulate('change', {target: {value: 'resolved'}});
    expect(ajax).not.toHaveBeenCalled();
  });

  it('serializes status updates for the same issue', () => {
    const pending = deferredRequest();
    const ajax = jest.spyOn($, 'ajax').mockImplementation(() => pending);
    const wrapper = shallow(<ProjectIssuesPanel projectId={7} canEdit={true} />);
    wrapper.setState({issues: [issue], loading: false});

    const statusControl = () => wrapper.find('select.project-issue-item__status');
    statusControl().simulate('change', {target: {value: 'in_review'}});

    expect(statusControl().prop('disabled')).toBe(true);
    expect(statusControl().prop('aria-busy')).toBe(true);
    statusControl().simulate('change', {target: {value: 'resolved'}});
    expect(ajax).toHaveBeenCalledTimes(1);

    pending.resolve({...issue, status: 'in_review'});

    expect(wrapper.state('issues')[0].status).toBe('in_review');
    expect(statusControl().prop('disabled')).toBe(false);
    expect(statusControl().prop('aria-busy')).toBe(false);
  });

  it('restores the status control after an update fails', () => {
    const pending = deferredRequest();
    jest.spyOn($, 'ajax').mockImplementation(() => pending);
    const wrapper = shallow(<ProjectIssuesPanel projectId={7} canEdit={true} />);
    wrapper.setState({issues: [issue], loading: false});

    wrapper.find('select.project-issue-item__status').simulate('change', {target: {value: 'resolved'}});
    pending.reject({responseText: 'Update rejected'});

    expect(wrapper.state('issues')[0].status).toBe('open');
    expect(wrapper.find('select.project-issue-item__status').prop('disabled')).toBe(false);
    expect(wrapper.text()).toContain('Update rejected');
  });
});
