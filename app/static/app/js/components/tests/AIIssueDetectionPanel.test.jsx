import React from 'react';
import { shallow } from 'enzyme';
import $ from 'jquery';

import AIIssueDetectionPanel from '../AIIssueDetectionPanel';

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

describe('<AIIssueDetectionPanel />', () => {
  beforeEach(() => {
    jest.spyOn($, 'getJSON').mockImplementation(() => completedRequest([{
      id: 'task-1',
      name: 'Latest orthophoto'
    }]));
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('labels the review region and announces request errors', () => {
    const pending = deferredRequest();
    $.getJSON.mockImplementationOnce(() => pending);
    const wrapper = shallow(<AIIssueDetectionPanel projectId={7} />);

    expect(wrapper.find('section.ai-issue-detection').prop('aria-label')).toBe('AI issue review');
    expect(wrapper.find('section.ai-issue-detection').prop('aria-busy')).toBe(true);
    expect(wrapper.find('[role="status"]')).toHaveLength(1);

    pending.reject({responseJSON: {detail: 'Tasks unavailable'}});
    expect(wrapper.find('.ai-issue-error').prop('role')).toBe('alert');
  });

  it('previews candidates and confirms the signed preview without rerunning it', () => {
    const preview = {
      model: 'gpt-test',
      source_count: 1,
      candidate_count: 1,
      candidates: [{
        title: 'Review roof edge',
        description: 'Possible damage is visible.',
        issue_type: 'defect',
        priority: 'high',
        confidence: 0.8,
        location_hint: 'north edge'
      }],
      confirmation_token: 'signed-preview'
    };
    const createdIssue = {
      id: 42,
      title: 'Review roof edge',
      status: 'in_review'
    };
    const ajax = jest.spyOn($, 'ajax')
      .mockImplementationOnce(() => completedRequest(preview))
      .mockImplementationOnce(() => completedRequest({issues: [createdIssue]}));
    const onIssuesCreated = jest.fn();
    const wrapper = shallow(
      <AIIssueDetectionPanel projectId={7} onIssuesCreated={onIssuesCreated} />
    );

    wrapper.find('form.ai-issue-controls').simulate('submit', {preventDefault: jest.fn()});

    expect(JSON.parse(ajax.mock.calls[0][0].data)).toEqual({
      source: 'auto',
      max_images: 3,
      create: false
    });
    expect(wrapper.find('.ai-issue-candidate')).toHaveLength(1);
    expect(wrapper.text()).toContain('Review roof edge');

    wrapper.find('.ai-issue-actions button').simulate('click');

    expect(JSON.parse(ajax.mock.calls[1][0].data)).toEqual({
      confirmation_token: 'signed-preview',
      create: true
    });
    expect(onIssuesCreated).toHaveBeenCalledWith([createdIssue]);
    expect(wrapper.text()).toContain('Created: 1');
    expect(wrapper.find('.ai-issue-actions button')).toHaveLength(0);
  });

  it('requires a task for orthophoto-only review', () => {
    const ajax = jest.spyOn($, 'ajax');
    const wrapper = shallow(<AIIssueDetectionPanel projectId={7} />);
    wrapper.setState({source: 'task_orthophoto', taskId: '', tasks: []});

    wrapper.find('form.ai-issue-controls').simulate('submit', {preventDefault: jest.fn()});

    expect(ajax).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Choose an orthophoto task.');
  });

  it('locks review inputs and prevents duplicate previews while a request is pending', () => {
    const pending = deferredRequest();
    const ajax = jest.spyOn($, 'ajax').mockImplementation(() => pending);
    const wrapper = shallow(<AIIssueDetectionPanel projectId={7} />);
    const submit = {preventDefault: jest.fn()};

    wrapper.find('form.ai-issue-controls').simulate('submit', submit);

    expect(wrapper.find('select').everyWhere(control => control.prop('disabled'))).toBe(true);
    expect(wrapper.find('input').prop('disabled')).toBe(true);
    expect(wrapper.find('button.ai-issue-preview-button').prop('disabled')).toBe(true);

    wrapper.find('form.ai-issue-controls').simulate('submit', submit);
    wrapper.instance().setSource({target: {value: 'field_photos'}});

    expect(ajax).toHaveBeenCalledTimes(1);
    expect(wrapper.state('source')).toBe('auto');

    pending.resolve({candidates: [], confirmation_token: 'signed-preview'});

    expect(wrapper.state('previewing')).toBe(false);
    expect(wrapper.state('preview').confirmation_token).toBe('signed-preview');
  });

  it('restores review controls after a preview request fails', () => {
    const pending = deferredRequest();
    jest.spyOn($, 'ajax').mockImplementation(() => pending);
    const wrapper = shallow(<AIIssueDetectionPanel projectId={7} />);

    wrapper.find('form.ai-issue-controls').simulate('submit', {preventDefault: jest.fn()});
    pending.reject({responseJSON: {detail: 'Provider unavailable'}});

    expect(wrapper.state('previewing')).toBe(false);
    expect(wrapper.find('select').first().prop('disabled')).toBe(false);
    expect(wrapper.find('button.ai-issue-preview-button').prop('disabled')).toBe(false);
    expect(wrapper.text()).toContain('Provider unavailable');
  });
});
